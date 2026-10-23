"""Shared Databricks syntax, identifier binding, and compiler-repair checks.

Only metadata-equivalent identifiers may be rebound. Unknown or ambiguous
business identifiers remain validation errors; they are never guessed.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel
from sqlglot.optimizer.scope import Scope, traverse_scope


def normalized_identifier(value: str) -> str:
    return value.casefold().replace('_', '')


def relation_key(table: exp.Table | str) -> tuple[str, ...]:
    if isinstance(table, str):
        table = sqlglot.parse_one(table, read='databricks', into=exp.Table)
    return tuple(part.name.casefold() for part in table.parts)


def parse_sql(sql: str) -> list[exp.Expression]:
    trees = [tree for tree in sqlglot.parse(sql, read='databricks', error_level=ErrorLevel.RAISE) if tree is not None]
    if not trees:
        raise ValueError('Empty SQL statement')
    if any(tree.find(exp.Command) is not None for tree in trees):
        raise ValueError('SQL uses syntax unsupported by the static Databricks parser; manual review is required')
    return trees


def split_sql(sql: str) -> list[str]:
    """Split only actual statement delimiters, preserving original SQL text."""
    parse_sql(sql)
    tokens = sqlglot.Dialect.get_or_raise('databricks').tokenize(sql)
    start, depth, blocks = 0, 0, 0
    parts = []
    for token in tokens:
        kind = token.token_type.name
        if kind == 'L_PAREN':
            depth += 1
        elif kind == 'R_PAREN':
            depth -= 1
        elif kind == 'BEGIN':
            blocks += 1
        elif kind == 'END' and blocks:
            blocks -= 1
        if kind == 'SEMICOLON' and not depth and not blocks:
            if sql[start:token.start].strip():
                parts.append(sql[start:token.start].strip())
            start = token.end + 1
    if sql[start:].strip():
        parts.append(sql[start:].strip())
    return parts


def _schemas(schemas: Mapping[Any, Any] | None) -> dict[tuple[str, ...], list[str]]:
    return {(relation_key(key) if isinstance(key, str) else key): list(value) for key, value in (schemas or {}).items()}


def _lookup(table: exp.Table, schemas: dict) -> list[str] | None:
    key = relation_key(table)
    if key in schemas:
        return schemas[key]
    # Unqualified names may refer to a unique current relation, never another catalog.
    matches = [columns for name, columns in schemas.items() if len(key) < 3 and name[-len(key):] == key]
    return matches[0] if len(matches) == 1 else None


def _query_roots(tree: exp.Expression):
    for query in tree.find_all(exp.Query):
        parent = query.parent
        while parent is not None and not isinstance(parent, exp.Query):
            parent = parent.parent
        if parent is None:
            yield query


def _output_columns(scope: Scope, schemas: dict) -> list[str]:
    result = []
    for projection in getattr(scope.expression, 'selects', []):
        if projection.is_star:
            for source in scope.sources.values():
                columns = _output_columns(source, schemas) if isinstance(source, Scope) else _lookup(source, schemas) if isinstance(source, exp.Table) else None
                result.extend(columns or [])
        elif projection.alias_or_name:
            result.append(projection.alias_or_name)
    return result


def _sources(scope: Scope, schemas: dict) -> dict[str, list[str] | None]:
    sources = {}
    for alias, source in scope.selected_sources.items():
        _, resolved = source
        columns = _output_columns(resolved, schemas) if isinstance(resolved, Scope) else _lookup(resolved, schemas) if isinstance(resolved, exp.Table) else None
        sources[alias.casefold()] = columns
    return sources


def _visible_sources(scope: Scope, schemas: dict, column: exp.Column) -> dict:
    sources = _sources(scope, schemas)
    # Only explicitly qualified correlated references may use an enclosing scope.
    parent = scope.parent
    while column.table and column.table.casefold() not in sources and parent:
        enclosing = _sources(parent, schemas)
        if column.table.casefold() in enclosing:
            sources[column.table.casefold()] = enclosing[column.table.casefold()]
            break
        parent = parent.parent
    return sources


def _physical_name(name: str, columns: list[str]) -> str | None:
    exact = [column for column in columns if column.casefold() == name.casefold()]
    if len(exact) == 1:
        return exact[0]
    candidates = [column for column in columns if normalized_identifier(column) == normalized_identifier(name)]
    if len(candidates) > 1:
        raise ValueError(f'Ambiguous physical column {name}')
    return candidates[0] if candidates else None


def bind_physical_columns(sql: str, schemas: Mapping[Any, Any], *, resolver=None) -> str:
    """Patch AST column-token offsets, preserving aliases, parameters, and literals."""
    available = _schemas(schemas)
    trees = parse_sql(sql)
    replacements: dict[tuple[int, int], str] = {}
    for tree in trees:
        parameters = {node.name.casefold() for udf in tree.find_all(exp.UserDefinedFunction) for node in udf.expressions if isinstance(node, exp.ColumnDef)}
        for root in _query_roots(tree):
            for scope in traverse_scope(root):
                sources = _sources(scope, available)
                for column in scope.columns:
                    if column.is_star or (not column.table and column.name.casefold() in parameters):
                        continue
                    selected = []
                    for alias, columns in _visible_sources(scope, available, column).items():
                        if columns is None or column.table and alias != column.table.casefold():
                            continue
                        physical = _physical_name(column.name, columns)
                        if physical:
                            selected.append((alias, physical))
                    if len(selected) != 1:
                        continue
                    selected_alias, physical = selected[0]
                    if resolver:
                        physical = resolver(scope, column, physical, selected_alias)
                    if physical == column.name:
                        continue
                    identifier = column.this
                    if 'start' not in identifier.meta:
                        raise ValueError('Cannot safely locate physical column token')
                    replacement = '`' + physical.replace('`', '``') + '`'
                    # Keep a generated view's standardized output name when reading raw Bronze.
                    if isinstance(column.parent, exp.Select):
                        replacement += ' AS `' + column.name.replace('`', '``') + '`'
                    replacements[(identifier.meta['start'], identifier.meta['end'] + 1)] = replacement
        _register_created(tree, available)
    for (start, end), replacement in sorted(replacements.items(), reverse=True):
        sql = sql[:start] + replacement + sql[end:]
    return sql


def _register_created(tree, schemas):
    if not isinstance(tree, exp.Create) or tree.kind not in {'TABLE', 'VIEW'}:
        return
    target = tree.this
    if isinstance(target, exp.Schema):
        if isinstance(target.this, exp.Table):
            schemas[relation_key(target.this)] = [column.name for column in target.expressions if isinstance(column, exp.ColumnDef)]
        return
    if isinstance(target, exp.Table):
        for root in _query_roots(tree):
            scopes = list(traverse_scope(root))
            if scopes:
                schemas[relation_key(target)] = _output_columns(scopes[-1], schemas)
                break


def output_schemas(sql: str, schemas: Mapping[Any, Any] | None = None) -> dict:
    available = _schemas(schemas)
    for tree in parse_sql(sql):
        _register_created(tree, available)
    return available


def validate_databricks_sql(sql: str, schemas: Mapping[Any, Any] | None = None, *, require_known_relations=False) -> list[str]:
    try:
        trees = parse_sql(sql)
    except (ValueError, sqlglot.errors.ParseError, sqlglot.errors.TokenError) as exc:
        return [f'SQL Syntax Error: {exc}']
    errors = []
    available = _schemas(schemas)
    for tree in trees:
        for select in tree.find_all(exp.Select):
            if not select.expressions:
                errors.append('SQL Syntax Error: SELECT requires a projection')
            aliases = [p.alias.casefold() for p in select.expressions if p.alias]
            if len(aliases) != len(set(aliases)):
                errors.append('Duplicate projected aliases within one SELECT')
        parameters = {node.name.casefold() for udf in tree.find_all(exp.UserDefinedFunction) for node in udf.expressions if isinstance(node, exp.ColumnDef)}
        for root in _query_roots(tree):
            for scope in traverse_scope(root):
                sources = _sources(scope, available)
                if require_known_relations:
                    for alias, columns in sources.items():
                        if columns is None:
                            errors.append(f'Unknown physical schema for relation {alias}')
                for column in scope.columns:
                    if column.is_star or not column.table and column.name.casefold() in parameters:
                        continue
                    if column.table:
                        visible = _visible_sources(scope, available, column)
                        if column.table.casefold() not in visible:
                            errors.append(f'Unknown relation alias {column.table}')
                        columns = visible.get(column.table.casefold())
                        if schemas is not None and columns is not None and column.name.casefold() not in {c.casefold() for c in columns}:
                            errors.append(f'Unknown physical column {column.sql(dialect="databricks")}')
                    else:
                        known = [cols for cols in sources.values() if cols is not None]
                        matches = sum(column.name.casefold() in {c.casefold() for c in cols} for cols in known)
                        # SELECT aliases are valid in GROUP BY, ORDER BY and HAVING.
                        output_alias = column.name.casefold() in {p.alias.casefold() for p in getattr(scope.expression, 'selects', []) if p.alias}
                        if matches > 1:
                            errors.append(f'Ambiguous physical column {column.name}')
                        elif schemas is not None and known and len(known) == len(sources) and not matches and not output_alias:
                            errors.append(f'Unknown physical column {column.name}')
                if isinstance(tree, exp.Create) and tree.kind == 'FUNCTION' and scope.expression.find(exp.From):
                    projections = getattr(scope.expression, 'selects', [])
                    aggregates = [agg for projection in projections for agg in projection.find_all(exp.AggFunc) if not agg.find_ancestor(exp.Window)]
                    if scope.expression.args.get('group') or not aggregates:
                        errors.append('Scalar SQL function queries must aggregate to one row without GROUP BY')
        if isinstance(tree, exp.Merge) and schemas is not None:
            target = _lookup(tree.this, available)
            using = tree.args.get('using')
            if isinstance(using, exp.Subquery):
                scopes = list(traverse_scope(using))
                source = _output_columns(scopes[-1], available) if scopes else None
            else:
                source = _lookup(using, available) if isinstance(using, exp.Table) else None
            merge_sources = {tree.this.alias_or_name.casefold(): target,
                             using.alias_or_name.casefold(): source} if using is not None else {}
            if require_known_relations and any(cols is None for cols in merge_sources.values()):
                errors.append('Unknown physical schema in MERGE')
            for column in tree.find_all(exp.Column):
                if column.find_ancestor(exp.Select):
                    continue
                columns = merge_sources.get(column.table.casefold()) if column.table else target
                if columns is not None and column.name.casefold() not in {c.casefold() for c in columns}:
                    errors.append(f'Unknown physical column {column.sql(dialect="databricks")}')
        _register_created(tree, available)
    return list(dict.fromkeys(errors))


def compile_probes(sql: str) -> list[str]:
    """Compile queries without executing DML or using out-of-scope UDF parameters."""
    probes = []
    for tree in parse_sql(sql):
        if isinstance(tree, exp.Create) and tree.kind == 'FUNCTION':
            body = tree.expression
            if not isinstance(body, exp.Return):
                raise ValueError('Function body requires live compilation review')
            values = {node.name.casefold(): exp.Cast(this=exp.Null(), to=node.args['kind'].copy()) for node in tree.this.expressions if isinstance(node, exp.ColumnDef)}
            query = exp.select(body.this.copy())
            for column in list(query.find_all(exp.Column)):
                if not column.table and column.name.casefold() in values:
                    column.replace(values[column.name.casefold()].copy())
            probes.append('EXPLAIN ' + query.sql(dialect='databricks'))
        elif isinstance(tree, exp.Create) and isinstance(tree.expression, exp.Query):
            probes.append('EXPLAIN ' + tree.expression.sql(dialect='databricks'))
        elif isinstance(tree, (exp.Merge, exp.Insert, exp.Update, exp.Delete, exp.Query)):
            probes.append('EXPLAIN ' + tree.sql(dialect='databricks'))
    return probes


def compiler_identifier_repair(sql: str, error: str) -> tuple[str, dict] | None:
    """Accept exactly one qualifier-preserving, case/underscore-equivalent suggestion."""
    if 'UNRESOLVED_COLUMN.WITH_SUGGESTION' not in error:
        return None
    match = re.search(r'(?:name|parameter)\s+(.+?)\s+cannot be resolved.*?Did you mean one of the following\?\s*\[([^\]]+)\]', error, re.I | re.S)
    if not match:
        return None
    def parts(value):
        value = value.strip().strip('. ')
        tokens = re.findall(r"`((?:``|[^`])+)`|'([^']+)'|([A-Za-z_]\w*)", value)
        return tuple(next(part for part in token if part).replace('``', '`') for token in tokens)
    wrong = parts(match.group(1))
    if not wrong or len(wrong) > 2:
        return None
    candidates = set()
    for value in match.group(2).split(','):
        candidate = parts(value)
        if len(candidate) != len(wrong) or normalized_identifier(candidate[-1]) != normalized_identifier(wrong[-1]):
            continue
        if tuple(p.casefold() for p in candidate[:-1]) != tuple(p.casefold() for p in wrong[:-1]):
            continue
        candidates.add(candidate)
    if len(candidates) != 1:
        return None
    candidate = candidates.pop()
    if candidate == wrong:
        return None
    trees = parse_sql(sql)
    replacements = {}
    for tree in trees:
        alias_relations = set()
        for root in _query_roots(tree):
            for scope in traverse_scope(root):
                for column in scope.columns:
                    if len(wrong) == 2 and column.table.casefold() == wrong[0].casefold() and column.name.casefold() == wrong[-1].casefold():
                        source = scope.sources.get(column.table)
                        if isinstance(source, exp.Table):
                            alias_relations.add(relation_key(source))
                        elif isinstance(source, Scope):
                            alias_relations.add(('derived', str(id(source))))
        if len(alias_relations) > 1:
            return None
        parameters = {node.name.casefold() for udf in tree.find_all(exp.UserDefinedFunction) for node in udf.expressions if isinstance(node, exp.ColumnDef)}
        for column in tree.find_all(exp.Column):
            if not column.table and column.name.casefold() in parameters:
                continue
            actual = (column.table, column.name) if column.table else (column.name,)
            if tuple(p.casefold() for p in actual) != tuple(p.casefold() for p in wrong):
                continue
            meta = column.this.meta
            if 'start' in meta:
                replacements[(meta['start'], meta['end'] + 1)] = '`' + candidate[-1].replace('`', '``') + '`'
    if not replacements:
        return None
    for (start, end), replacement in sorted(replacements.items(), reverse=True):
        sql = sql[:start] + replacement + sql[end:]
    if validate_databricks_sql(sql):
        return None
    return sql, {'from_identifier': '.'.join(wrong), 'to_identifier': '.'.join(candidate), 'replacement_count': len(replacements)}
