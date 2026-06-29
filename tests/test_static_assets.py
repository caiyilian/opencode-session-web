import re

import app as webapp


def test_index_versions_static_assets():
    app = webapp.create_app({"TESTING": True})

    with app.test_client() as client:
        response = client.get("/")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert re.search(r"/static/css/main\.css\?v=\d+", body)
    assert re.search(r"/static/js/app\.js\?v=\d+", body)
