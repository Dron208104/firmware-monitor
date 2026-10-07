from pathlib import Path

ROOT=Path(__file__).parents[1]
CSS=(ROOT/"app"/"static"/"version-source.css").read_text(encoding="utf-8")
LAYOUT=(ROOT/"app"/"static"/"modal-layout.css").read_text(encoding="utf-8")
HTML=(ROOT/"app"/"templates"/"device_modal.html").read_text(encoding="utf-8")

def test_modal_uses_viewport_safe_three_part_layout():
    assert "max-height:calc(100dvh - 32px)" in CSS
    assert ".modal-card form{flex:1 1 auto;min-height:0;overflow:hidden}" in CSS
    assert ".modal-scroll{flex:1 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden" in CSS
    assert ".modal-card footer{flex:0 0 auto}" in CSS
    assert "height: min(688px, calc(100dvh - 32px))" in LAYOUT

def test_source_switch_is_full_width_and_equal_columns():
    assert ".source-tabs{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in CSS
    assert "width:100%;max-width:none" in CSS

def test_mobile_layout_has_safe_inset_and_single_column():
    assert "@media(max-width:639px)" in CSS
    assert ".modal{padding:8px;place-items:center}" in CSS
    assert "max-height:calc(100dvh - 16px)" in CSS
    assert ".modal-grid{grid-template-columns:minmax(0,1fr)" in CSS

def test_required_marks_share_label_line():
    assert '<span>Название <b>*</b></span>' in HTML
    assert '<span>IP-адрес <b>*</b></span>' in HTML

def test_optional_hardware_revision_is_actually_hidden():
    assert ".modal-grid > [hidden] { display: none !important; }" in LAYOUT
    assert "select.required=required" in (ROOT/"app"/"static"/"app.js").read_text(encoding="utf-8")

def test_comment_field_is_available_when_creating_device():
    assert '<span>Комментарий</span><textarea name="description"' in HTML

def test_equipment_icon_picker_offers_switch_and_router():
    picker=(ROOT/"app"/"static"/"device-icon-picker.css").read_text(encoding="utf-8")
    assert 'name="icon_type" value="switch" checked' in HTML
    assert 'name="icon_type" value="router"' in HTML
    assert ".device-icon-options" in picker
    assert "input:checked+span" in picker
