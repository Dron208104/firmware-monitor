from pathlib import Path

JS=(Path(__file__).parents[1]/"app"/"static"/"app.js").read_text(encoding="utf-8")
CSS=(Path(__file__).parents[1]/"app"/"static"/"style.css").read_text(encoding="utf-8")
FOLDERS_CSS=(Path(__file__).parents[1]/"app"/"static"/"folders.css").read_text(encoding="utf-8")
IDENTITY_CSS=(Path(__file__).parents[1]/"app"/"static"/"device-identity.css").read_text(encoding="utf-8")
BLUE_CSS=(Path(__file__).parents[1]/"app"/"static"/"blue-theme.css").read_text(encoding="utf-8")
TABLE_CSS=(Path(__file__).parents[1]/"app"/"static"/"device-table.css").read_text(encoding="utf-8")
DASHBOARD_JS=(Path(__file__).parents[1]/"app"/"static"/"dashboard-ui.js").read_text(encoding="utf-8")

def test_firmware_actions_depend_on_backend_urls():
    assert "if(device.download_url&&device.status==='Есть обновление')" in JS
    assert "if(device.changelog_url)" in JS
    assert "link.href=device.download_url" in JS
    assert "link.href=device.changelog_url" in JS
    assert "WEB" not in JS and "'DL'" not in JS and "'LOG'" not in JS

def test_external_actions_are_safe_and_accessible():
    assert "noopener noreferrer" in JS
    assert "aria-label" in JS
    assert "Скачать прошивку ${device.available_version}" in JS
    assert "Посмотреть изменения в версии ${device.available_version}" in JS

def test_rare_actions_are_in_more_menu_and_narrow_layout_exists():
    assert "action-more" in JS and "Открыть страницу производителя" in JS and "Удалить устройство" in JS
    assert "@media(max-width:1180px)" in CSS
    assert ".firmware-download span,.row-actions .firmware-changelog span{display:none}" in CSS

def test_check_button_has_busy_state():
    assert "button.disabled=true" in JS and "button.disabled=false" in JS
    assert "Проверяем версии…" in JS

def test_primary_and_secondary_actions_are_separated():
    assert "device.download_url&&device.status==='Есть обновление'" in JS
    assert "menu.append(edit)" in JS and "menu.append(check)" in JS
    assert "Действия с устройством ${device.name}" in JS
    assert "e.key==='Escape'" in JS
    assert "menu-danger" in JS

def test_changelog_localization_observer_does_not_loop_forever():
    assert "if(label.textContent!=='Изменения')" in JS

def test_successful_create_reloads_canonical_table_row_and_blocks_duplicates():
    assert "if(submit.disabled)return;submit.disabled=true" in JS
    submit_handler=JS[JS.index("form?.addEventListener('submit'"):JS.index("const search=")]
    assert "location.reload()" in submit_handler
    assert "tbody.append(rowFor(result))" not in submit_handler

def test_device_table_supports_name_ip_sorting_and_comments():
    assert "const columns=[['device','Устройство'],['ip','IP-адрес']]" in JS
    assert "const compareIp=" in JS
    assert "firmware-monitor-device-columns" not in JS
    assert "draggable=true" not in JS
    assert "device.description||''" in JS
    assert "device-comment" in JS

def test_device_name_and_description_have_compact_identity_layout():
    html=(Path(__file__).parents[1]/"app"/"templates"/"dashboard.html").read_text(encoding="utf-8")
    assert 'class="device-name{{\' has-description\' if d.description}}" data-description="{{d.description or \'\'}}"' in html
    assert '<small class="device-model" title="{{d.model}}">{{d.model}}' in html
    assert 'href="/static/device-identity.css?v=1"' in html
    assert "identity.className='device-copy'" in JS
    assert "description.className='device-comment'" in JS
    assert ".table-wrap { overflow-x: hidden; }" in IDENTITY_CSS
    assert "min-width: 0; table-layout: fixed" in IDENTITY_CSS

def test_missing_firmware_actions_have_disabled_placeholders():
    assert "const alignFirmwareActions=" in JS
    assert "const disabledFirmwareAction=" in JS
    assert "Ссылка на прошивку недоступна" in JS
    assert "Описание изменений недоступно" in JS
    assert "button.disabled=true" in JS
    assert "actions.replaceChildren(download,changelog,more)" in JS


def test_shared_dialog_assets_replace_native_browser_dialogs():
    root=Path(__file__).parents[1]
    base=(root/"app/templates/base.html").read_text(encoding="utf-8")
    dialog_js=(root/"app/static/dialog-system.js").read_text(encoding="utf-8")
    all_js="\n".join(path.read_text(encoding="utf-8") for path in (root/"app/static").glob("*.js"))
    assert '/static/dialogs.css?v=1' in base
    assert '/static/dialog-system.js?v=1' in base
    assert "requireConfirmation" in dialog_js and "showModal()" in dialog_js
    assert not __import__("re").search(r"(?<![.\w])(confirm|prompt|alert)\s*\(",all_js)
    assert ".firmware-action-placeholder" in FOLDERS_CSS
    assert "grid-template-columns:86px 104px 30px" in FOLDERS_CSS
    assert "cursor:not-allowed" in FOLDERS_CSS
    assert "finally{submit.disabled=false}" in JS

def test_firmware_action_columns_keep_all_four_states_aligned():
    assert "actions.querySelector('.firmware-download')||disabledFirmwareAction" in JS
    assert "actions.querySelector('.firmware-changelog')||disabledFirmwareAction" in JS
    assert "grid-column:1" in FOLDERS_CSS
    assert "grid-column:2" in FOLDERS_CSS
    assert "grid-column:3" in FOLDERS_CSS
    assert ":disabled:hover" in FOLDERS_CSS
    assert ".row-actions>.firmware-download,.dashboard-equipment .row-actions>.firmware-changelog{display:grid!important" in BLUE_CSS
    assert ".row-actions>.firmware-action-placeholder{display:none" not in BLUE_CSS
    assert ".firmware-action-placeholder{display:grid!important" in TABLE_CSS
    assert "cursor:not-allowed!important" in TABLE_CSS

def test_device_delete_uses_application_dialog_with_confirmation_checkbox():
    html=(Path(__file__).parents[1]/"app"/"templates"/"dashboard.html").read_text(encoding="utf-8")
    assert 'id="device-delete-dialog"' in html
    assert "data-delete-confirm-check" in html and "data-delete-confirm-button disabled" in html
    assert "confirm('Удалить устройство?')" not in html
    assert "confirm('Удалить устройство?" not in JS
    assert "confirmButton.disabled=!checkbox.checked" in JS
    assert "pendingDeleteForm.submit()" in JS
    assert "pendingDeleteButton=button" in JS
    assert ".device-delete-dialog" in FOLDERS_CSS
    assert "grid-template-columns:44px minmax(0,1fr)" in FOLDERS_CSS
    assert ".device-delete-confirm:has(input:checked)" in FOLDERS_CSS

def test_equipment_empty_states_are_mutually_exclusive():
    html=(Path(__file__).parents[1]/"app"/"templates"/"dashboard.html").read_text(encoding="utf-8")
    assert 'data-total-devices="{{counts.total}}"' in html
    assert "{% if counts.total==0 %}" in html
    assert 'id="devices-empty"' in html
    assert 'id="filtered-empty" hidden' in html
    assert html.index('id="devices-empty"') < html.index("{% else %}",html.index("{% if counts.total==0 %}"))
    assert html.index('id="filtered-empty"') > html.index("{% else %}",html.index("{% if counts.total==0 %}"))
    assert "let totalDevices=Number(" in JS
    assert "hasAnyDevices=totalDevices>0,hasVisibleDevices=visible>0" in JS
    assert "table.hidden=!hasVisibleDevices" in JS
    assert "if(!hasAnyDevices){noResults?.remove()" in JS
    assert "emptyDevices.hidden=true" in JS
    assert "noResults.hidden=hasVisibleDevices" in JS

def test_equipment_no_results_can_reset_filters_and_check_all_is_disabled_when_empty():
    html=(Path(__file__).parents[1]/"app"/"templates"/"dashboard.html").read_text(encoding="utf-8")
    assert "data-reset-equipment-filters" in html
    assert "Сбросить фильтры" in html
    assert "counts.total==0" in html and 'disabled title="Нет устройств для проверки"' in html
    assert "activeFolder='all';search.value='';vendor.value='';status.value=''" in JS
    assert '[data-total-devices="0"] #filtered-empty{display:none!important}' in FOLDERS_CSS
    assert '[data-total-devices="0"] #devices-empty{display:block!important}' in FOLDERS_CSS

def test_device_table_paginates_and_activity_feed_scrolls_inside_panel():
    html=(Path(__file__).parents[1]/"app"/"templates"/"dashboard.html").read_text(encoding="utf-8")
    assert 'data-device-pagination' in html
    assert 'data-device-page-previous' in html and 'data-device-page-next' in html
    assert 'const devicePageSize=6' in JS
    assert 'pagedDeviceRows.slice(start,end)' in JS
    assert 'if(resetPage)devicePage=1' in JS
    assert '.device-pagination[hidden]{display:none!important}' in TABLE_CSS
    assert '.activity-list{min-height:0!important;max-height:none!important;flex:1 1 auto;overflow-y:auto!important' in TABLE_CSS
    assert "new ResizeObserver(syncActivityHeight).observe(equipmentPanel)" in DASHBOARD_JS
    assert "Math.max(440,devicePanel?.scrollHeight||0,folderPanel?.scrollHeight||0)" in DASHBOARD_JS
    assert "workspace?.style.setProperty('--dashboard-row-height'" in DASHBOARD_JS
    assert ".dashboard-workspace{align-items:start!important}" in TABLE_CSS
    assert "height:var(--dashboard-row-height,440px)!important" in TABLE_CSS
