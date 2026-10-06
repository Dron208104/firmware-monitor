from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "app/templates/dashboard.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/device-table.css").read_text(encoding="utf-8")
FIRMWARE_JS = (ROOT / "app/static/firmware-display.js").read_text(encoding="utf-8")
DESCRIPTION_JS = (ROOT / "app/static/device-description.js").read_text(encoding="utf-8")


def test_connection_method_has_own_column_and_ip_never_wraps():
    assert 'data-column="connection">Подключение' in HTML
    assert "d.acquisition_method=='manual'" in HTML
    assert 'td[data-column="ip"]{white-space:nowrap' in CSS
    assert 'row.querySelector(\'[data-column="connection"]\')' in JS
    assert 'data-column="model" hidden' in HTML


def test_columns_have_canonical_order_and_only_name_ip_are_sortable():
    expected = ["device", "ip", "connection", "installed", "status", "checked", "actions"]
    for column in expected:
        assert f'data-column="{column}"' in HTML
    header = HTML[HTML.index("<thead>"):HTML.index("</thead>")]
    positions = [header.index(f'data-column="{column}"') for column in expected]
    assert positions == sorted(positions)
    assert "const columns=[['device','Устройство'],['ip','IP-адрес']]" in JS
    assert "dragstart" not in JS and "applyColumnOrder" not in JS


def test_vendor_model_and_versions_are_grouped_for_a_compact_dashboard():
    assert 'class="device-model"' in HTML
    assert '<small class="device-model" title="{{d.model}}">{{d.model}}' in HTML
    assert 'class="firmware-available"' in HTML
    assert 'data-column="available" hidden' in HTML
    assert "device.available_version" in FIRMWARE_JS
    assert "arrow.textContent='→'" in FIRMWARE_JS
    assert "updateStatuses.has(device.status)" in FIRMWARE_JS


def test_action_column_is_compact_and_fits_inside_table():
    assert '[data-column="actions"]{width:112px!important;min-width:112px!important' in CSS
    assert "grid-template-columns:30px 30px 30px!important" in CSS
    assert ".firmware-download span" in CSS and "display:none!important" in CSS


def test_device_description_stays_on_one_line_with_full_text_tooltip():
    assert 'data-description="{{d.description or \'\'}}"' in HTML
    assert "target?.dataset.description?.trim()" in DESCRIPTION_JS
    assert "tooltip.className='device-description-tooltip'" in DESCRIPTION_JS
    assert '{{d.vendor}} · {{d.model}}' not in HTML
