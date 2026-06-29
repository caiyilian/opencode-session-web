import re

import app as webapp


def test_index_versions_static_assets():
    app = webapp.create_app({"TESTING": True})

    with app.test_client() as client:
        response = client.get("/")
        asset_response = client.get("/frontend/assets/index.js")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert re.search(r"/static/css/main\.css\?v=\d+", body)
    assert re.search(r"/static/js/app\.js\?v=\d+", body)
    assert asset_response.status_code == 404


def test_index_serves_frontend_dist_when_enabled(tmp_path):
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        '<div id="root"></div><script type="module" src="/frontend/assets/index.js"></script>',
        encoding="utf-8",
    )
    (assets_dir / "index.js").write_text("console.log('react build');", encoding="utf-8")
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_USE_FRONTEND_DIST": True,
            "OPENCODE_FRONTEND_DIST_DIR": str(dist_dir),
        }
    )

    with app.test_client() as client:
        index_response = client.get("/")
        asset_response = client.get("/frontend/assets/index.js")

    body = index_response.get_data(as_text=True)
    assert index_response.status_code == 200
    assert '<div id="root"></div>' in body
    assert "/frontend/assets/index.js" in body
    assert "/static/js/app.js" not in body
    assert asset_response.status_code == 200
    assert "react build" in asset_response.get_data(as_text=True)


def test_index_falls_back_when_frontend_dist_missing(tmp_path):
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_USE_FRONTEND_DIST": True,
            "OPENCODE_FRONTEND_DIST_DIR": str(tmp_path / "missing-dist"),
        }
    )

    with app.test_client() as client:
        response = client.get("/")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert re.search(r"/static/js/app\.js\?v=\d+", body)
