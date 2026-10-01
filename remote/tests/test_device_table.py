from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "app/templates/dashboard.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/device-table.css").read_text(encoding="utf-8")


def test_connection_method_has_own_column_and_ip_never_wraps():
    assert 'data-column="connection">Подключение' in HTML
    assert "d.acquisition_method=='manual'" in HTML
    assert 'td[data-column="ip"]{white-space:nowrap' in CSS
    assert 'row.querySelector(\'[data-column="connection"]\').textContent=device.connection_type' in JS


def test_columns_have_canonical_order_and_only_name_ip_are_sortable():
    expected = ["device", "ip", "vendor", "model", "connection", "installed", "available", "status", "checked", "actions"]
    for column in expected:
        assert f'data-column="{column}"' in HTML
    header = HTML[HTML.index("<thead>"):HTML.index("</thead>")]
    positions = [header.index(f'data-column="{column}"') for column in expected]
    assert positions == sorted(positions)
    assert "const columns=[['device','Устройство'],['ip','IP-адрес']]" in JS
    assert "dragstart" not in JS and "applyColumnOrder" not in JS


def test_action_column_is_compact_and_fits_inside_table():
    assert '[data-column="actions"]{width:112px!important;min-width:112px!important' in CSS
    assert "grid-template-columns:30px 30px 30px!important" in CSS
    assert ".firmware-download span" in CSS and "display:none!important" in CSS


def test_device_description_stays_on_one_line_with_full_text_tooltip():
    assert 'class="device-comment" title="{{d.description}}"' in HTML
    assert '.device-comment{display:block;max-width:100%!important' in CSS
    assert 'text-overflow:ellipsis!important;white-space:nowrap!important' in CSS
