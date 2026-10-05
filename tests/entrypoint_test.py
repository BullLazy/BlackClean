import uvicorn

from blackclean.cli import main


def test_cli_entrypoint_starts_fastapi_app(monkeypatch):
    called = {}

    def fake_run(application, **kwargs):
        called["application"] = application
        called["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)

    main()

    assert called["application"] == "blackclean.main:app"
    assert called["kwargs"] == {"host": "127.0.0.1", "port": 8000}
