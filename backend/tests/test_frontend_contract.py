from pathlib import Path

def test_frontend_has_no_recovery_placeholder():
    app = (Path(__file__).parents[2] / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "Module not yet wired in this recovery build" not in app
    assert "Run assessment" in app
    assert "Generate plans" in app
    assert "Run discovery" in app
    assert "Build {BUILD_VERSION}" in app
    assert "Semantic Medallion Factory" in app
    assert "Infer fact/dimension" in app
    assert "Analyze consumers" in app
    assert "Generate stage artifacts" in app
    assert "2.3.0 SEMANTIC_MEDALLION_FACTORY" in app

def test_frontend_api_uses_same_origin_api_for_production():
    api = (Path(__file__).parents[2] / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
    assert "import.meta.env.VITE_API_URL||'/api'" in api

    vite = (Path(__file__).parents[2] / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "'/api': 'http://127.0.0.1:8000'" in vite
