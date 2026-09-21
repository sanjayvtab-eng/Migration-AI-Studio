"""Bind routine column references to known relation schemas without changing SQL values.

This deliberately handles static relation references only. Unknown/derived relations
shadow outer aliases; ambiguous bare references are reported rather than guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.engine import _function_parameter_declarations, _function_signature, _sql_code, qident


@dataclass
class Token:
    value: str
    start: int
    end: int
    scope: int


IDENT = r"`(?:``|[^`])+`|[A-Za-z_]\w*"
KEYWORDS = set("""SELECT FROM JOIN INNER LEFT RIGHT FULL OUTER CROSS ON WHERE GROUP BY
ORDER HAVING QUALIFY LIMIT OFFSET UNION ALL DISTINCT AS INTO INSERT UPDATE SET
DELETE MERGE USING WHEN MATCHED THEN VALUES RETURN BEGIN END LANGUAGE SQL RETURNS
READS DATA SECURITY INVOKER AND OR NOT NULL IS IN EXISTS CASE ELSE ASC DESC WITH
OVER PARTITION CAST INT DECIMAL STRING TIMESTAMP COUNT SUM COALESCE TRUE FALSE
OVERWRITE TABLE""".lower().split())


def _name(value: str) -> str:
    return value.strip('`').replace('``', '`').lower()


def bind_columns(sql: str, relations: dict[tuple[str, ...], dict[str, str]]) -> tuple[str, list[str]]:
    """Return SQL with source column spellings bound to their planned target names.

    Relation keys are exact identifier tuples; column maps include both source and
    target spellings. Formatting, routine parameters, output aliases and literals
    remain intact. The caller decides whether to publish a new governed version.
    """
    code = _sql_code(sql)
    signature = _function_signature(sql)
    routine_name = tuple(_name(part) for part in re.findall(IDENT, signature.group(1))) if signature else ()
    parameters = {_name(parts[-1]) for _, _, parts in _function_parameter_declarations(sql)}
    tokens: list[Token] = []
    parents = {0: None}
    stack = [0]
    next_scope = 0
    for match in re.finditer(rf"{IDENT}|[().,;]|\S", code):
        value = match.group()
        if value == ')' and len(stack) > 1:
            stack.pop()
        tokens.append(Token(value, match.start(), match.end(), stack[-1]))
        if value == '(':
            next_scope += 1
            parents[next_scope] = stack[-1]
            stack.append(next_scope)
        elif value == ';':
            next_scope += 1
            parents[next_scope] = None
            stack = [next_scope]
        elif value.upper() == 'UNION':
            next_scope += 1
            parents[next_scope] = parents[stack[-1]]
            stack[-1] = next_scope

    def identifier(index: int) -> bool:
        return 0 <= index < len(tokens) and bool(re.fullmatch(IDENT, tokens[index].value))

    def chain(index: int) -> tuple[list[int], int]:
        parts = [index]
        end = index + 1
        while end + 1 < len(tokens) and tokens[end].value == '.' and identifier(end + 1):
            parts.append(end + 1)
            end += 2
        return parts, end

    body_start = 0
    for token in tokens:
        if token.value.upper() in {'FUNCTION', 'PROCEDURE'}:
            boundary = 'RETURN' if token.value.upper() == 'FUNCTION' else 'BEGIN'
            body_start = next((item.start for item in tokens if item.start > token.start and item.value.upper() == boundary), len(sql))
            break
    aliases: dict[int, dict[str, dict[str, str] | None]] = {}
    query_scopes = set()
    protected = set()
    inserts: dict[int, dict[str, str]] = {}
    from_list = {}
    output_aliases: dict[int, set[str]] = {}
    for index, token in enumerate(tokens):
        if token.start < body_start:
            protected.add(index)
            continue
        if token.value.upper() in {'SELECT', 'UPDATE', 'MERGE'}:
            query_scopes.add(token.scope)
        if token.value.upper() in {'FROM', 'JOIN'}:
            from_list[token.scope] = True
        elif token.value.upper() in {'WHERE', 'ON', 'GROUP', 'ORDER', 'HAVING', 'QUALIFY', 'LIMIT', 'UNION'}:
            from_list[token.scope] = False
        relation_start = token.value.upper() in {'FROM', 'JOIN', 'INTO', 'UPDATE', 'USING', 'OVERWRITE'}
        relation_start |= token.value == ',' and from_list.get(token.scope, False)
        if not relation_start:
            continue
        start_index = index + 1
        if token.value.upper() in {'INTO', 'OVERWRITE'} and start_index < len(tokens) and tokens[start_index].value.upper() == 'TABLE':
            protected.add(start_index)
            start_index += 1
        if start_index < len(tokens) and tokens[start_index].value == '(':
            depth = 1
            end = start_index + 1
            while end < len(tokens) and depth:
                depth += (tokens[end].value == '(') - (tokens[end].value == ')')
                end += 1
            alias_index = end + 1 if end < len(tokens) and tokens[end].value.upper() == 'AS' else end
            if identifier(alias_index) and _name(tokens[alias_index].value) not in KEYWORDS:
                aliases.setdefault(token.scope, {})[_name(tokens[alias_index].value)] = None
                protected.add(alias_index)
            continue
        if not identifier(start_index):
            continue
        parts, end = chain(start_index)
        key = tuple(_name(tokens[p].value) for p in parts)
        schema = relations.get(key)
        protected.update(parts)
        scope_aliases = aliases.setdefault(token.scope, {})
        alias_index = end + 1 if end < len(tokens) and tokens[end].value.upper() == 'AS' else end
        if identifier(alias_index) and _name(tokens[alias_index].value) not in KEYWORDS:
            scope_aliases[_name(tokens[alias_index].value)] = schema
            protected.add(alias_index)
        else:
            scope_aliases[key[-1]] = schema
        if token.value.upper() in {'INTO', 'OVERWRITE'} and schema is not None and end < len(tokens) and tokens[end].value == '(':
            if end + 1 < len(tokens):
                inserts[tokens[end + 1].scope] = schema

    for index, token in enumerate(tokens[:-1]):
        if token.value.upper() == 'AS' and token.scope in query_scopes and identifier(index + 1) and index + 1 not in protected:
            output_aliases.setdefault(token.scope, set()).add(_name(tokens[index + 1].value))

    def visible(scope: int) -> dict[str, dict[str, str] | None]:
        result = {}
        while scope is not None:
            for alias, schema in aliases.get(scope, {}).items():
                result.setdefault(alias, schema)
            scope = parents[scope]
        return result

    def in_query(scope: int) -> bool:
        while scope is not None:
            if scope in query_scopes:
                return True
            scope = parents[scope]
        return False

    def bare_tables(scope: int, name: str) -> list[dict[str, str] | None]:
        # Local query columns take precedence over correlated outer columns.
        while scope is not None:
            tables = list(aliases.get(scope, {}).values())
            if any(table is None or name in table for table in tables):
                return tables
            scope = parents[scope]
        return []

    edits = []
    errors = []
    clauses = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not identifier(index):
            index += 1
            continue
        parts, end = chain(index)
        names = [_name(tokens[p].value) for p in parts]
        index = end
        if token.value.upper() in {'SELECT', 'FROM', 'WHERE', 'GROUP', 'ORDER', 'HAVING', 'QUALIFY'}:
            clauses[token.scope] = token.value.upper()
        if any(p in protected for p in parts):
            continue
        if names[-1] in parameters and tuple(names[:-1]) in {routine_name, routine_name[-1:]}:
            continue
        # Calls, declaration names and projected aliases are not column references.
        if end < len(tokens) and tokens[end].value == '(':
            continue
        before = tokens[parts[0] - 1].value.upper() if parts[0] else ''
        if before in {'AS', 'DECLARE', 'FUNCTION', 'PROCEDURE'}:
            continue
        schema = None
        if len(parts) == 2:
            schema = visible(token.scope).get(names[0])
        elif len(parts) > 2:
            schema = relations.get(tuple(names[:-1]))
        elif token.scope in inserts:
            schema = inserts[token.scope]
        elif names[0] not in KEYWORDS and in_query(token.scope):
            if clauses.get(token.scope) == 'ORDER' and names[0] in output_aliases.get(token.scope, set()):
                continue
            tables = bare_tables(token.scope, names[0])
            candidates = [table for table in tables if table is not None and names[0] in table]
            if candidates and (len(candidates) != 1 or any(table is None for table in tables)):
                if any(table[names[0]].lower() != names[0] for table in candidates):
                    errors.append(f"Ambiguous routine column {tokens[parts[-1]].value}; qualify it with its relation alias")
                continue
            schema = candidates[0] if candidates else None
        if schema is None:
            continue
        column = tokens[parts[-1]]
        target = schema.get(names[-1])
        if target is None:
            errors.append(f"Unknown routine column {column.value} on its referenced relation; available columns: "
                          + ', '.join(sorted(set(schema.values()))))
        elif target.lower() != names[-1]:
            edits.append((column.start, column.end, qident(target)))
    for start, end, replacement in reversed(edits):
        sql = sql[:start] + replacement + sql[end:]
    return sql, list(dict.fromkeys(errors))
