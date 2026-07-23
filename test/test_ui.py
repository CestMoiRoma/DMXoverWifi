"""Browser-level checks of the web UI, driven against the mock board.

These are the tests that would have caught a broken nav button or a channel
control that posts the wrong value, which no amount of Python-side testing can
see. Skipped automatically when playwright is not installed, so the rest of the
suite still runs on a bare machine.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "ui"))

from browser import NoBrowserFound, launch_chromium  # noqa: E402
from mock_server import serve_in_background  # noqa: E402

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed; run the suite in Docker for UI tests"
)


@pytest.fixture(scope="module")
def board():
    """A mock board serving the real www/ files, shared by the UI tests."""
    server, state, url = serve_in_background()
    yield {"url": url, "state": state}
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as pw:
        try:
            instance = launch_chromium(pw)
        except NoBrowserFound as exc:
            pytest.skip(str(exc))
        yield instance
        instance.close()


@pytest.fixture
def page(browser, board):
    page = browser.new_page(viewport={"width": 900, "height": 1200})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(board["url"], wait_until="networkidle")
    page.wait_for_timeout(300)
    yield page
    assert errors == [], "the page threw: %s" % errors
    page.close()


def show(page, view):
    page.click('.nav-btn[data-view="%s"]' % view)
    page.wait_for_timeout(300)


# -- navigation ------------------------------------------------------------


def test_every_nav_button_reaches_its_page(page):
    for view in ("home", "devices", "settings", "info", "home"):
        show(page, view)
        assert page.is_visible("#view-" + view)
        assert "active" in (page.get_attribute('.nav-btn[data-view="%s"]' % view, "class") or "")


def test_only_one_page_is_visible_at_a_time(page):
    show(page, "settings")

    visible = page.eval_on_selector_all(
        ".view", "nodes => nodes.filter(n => n.classList.contains('active')).length"
    )
    assert visible == 1


def test_the_app_opens_on_the_home_page(page):
    assert page.is_visible("#view-home")


# -- home: live control ----------------------------------------------------


def test_home_lists_every_configured_fixture(page):
    assert page.inner_text("#view-home").count("PAR LED") == 1
    assert "Smoke machine" in page.inner_text("#view-home")


def test_sliders_render_for_slider_channels(page):
    assert page.eval_on_selector_all('#view-home input[type="range"]', "n => n.length") == 4


def test_each_button_channel_type_renders_its_own_control(page):
    labels = page.eval_on_selector_all(
        "#view-home .channel-btn", "nodes => nodes.map(n => n.textContent.trim())"
    )
    assert labels == ["Trigger", "Hold", "Off"]


def test_moving_a_slider_posts_the_value(page, board):
    board["state"]["channel_writes"].clear()

    page.eval_on_selector(
        '#view-home input[type="range"]',
        """node => {
            node.value = 180;
            node.dispatchEvent(new Event('input', { bubbles: true }));
            node.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
    )
    page.wait_for_timeout(300)

    assert board["state"]["channel_writes"][-1] == {
        "device": "dev-a1b2c3",
        "offset": 1,
        "value": 180,
    }


def test_the_slider_readout_follows_the_handle(page):
    page.eval_on_selector(
        '#view-home input[type="range"]',
        "node => { node.value = 99; node.dispatchEvent(new Event('input', {bubbles: true})); }",
    )
    assert page.inner_text("#view-home .channel-control span") == "99"


def test_a_trigger_button_fires_full_on(page, board):
    board["state"]["channel_writes"].clear()

    page.click("#view-home .channel-btn:not(.momentary):not(.switch)")
    page.wait_for_timeout(300)

    assert board["state"]["channel_writes"] == [
        {"device": "dev-d4e5f6", "offset": 1, "value": 255}
    ]


def test_a_momentary_button_sends_on_press_and_off_on_release(page, board):
    board["state"]["channel_writes"].clear()

    button = page.query_selector("#view-home .channel-btn.momentary")
    box = button.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(200)
    page.mouse.up()
    page.wait_for_timeout(300)

    values = [w["value"] for w in board["state"]["channel_writes"]]
    assert values == [255, 0], "hold must go full on, release must go back to zero"
    assert all(w["offset"] == 2 for w in board["state"]["channel_writes"])


def test_a_switch_button_latches_on_then_off(page, board):
    board["state"]["channel_writes"].clear()
    button = page.query_selector("#view-home .channel-btn.switch")

    button.click()
    page.wait_for_timeout(250)
    assert button.inner_text().strip() == "On"

    button.click()
    page.wait_for_timeout(250)
    assert button.inner_text().strip() == "Off"

    assert [w["value"] for w in board["state"]["channel_writes"]] == [255, 0]


# -- device manager --------------------------------------------------------


def test_device_manager_lists_fixtures_with_their_addresses(page):
    show(page, "devices")
    text = page.inner_text("#device-list")

    assert "PAR LED (start ch. 1)" in text
    assert "Smoke machine (start ch. 10)" in text


def test_device_manager_shows_each_channel_with_its_type(page):
    show(page, "devices")
    text = page.inner_text("#device-list")

    assert "1: Dimmer (slider)" in text
    assert "2: Blast (button-momentary)" in text
    assert "3: Heater (button-switch)" in text


def test_the_channel_editor_offers_all_four_types(page):
    show(page, "devices")
    page.click("#add-channel-row")

    options = page.eval_on_selector_all(
        "#channel-rows .ch-type option", "nodes => nodes.map(n => n.value)"
    )
    assert options == ["slider", "button", "button-momentary", "button-switch"]


def test_adding_channel_rows_pre_fills_increasing_offsets(page):
    show(page, "devices")
    page.click("#add-channel-row")
    page.click("#add-channel-row")

    offsets = page.eval_on_selector_all(
        "#channel-rows .ch-offset", "nodes => nodes.map(n => n.value)"
    )
    assert offsets == ["1", "2"]


def test_a_channel_row_can_be_removed_again(page):
    show(page, "devices")
    page.click("#add-channel-row")
    page.click("#channel-rows .channel-row button")

    assert page.eval_on_selector_all("#channel-rows .channel-row", "n => n.length") == 0


def test_creating_a_fixture_adds_it_to_the_list(page, board):
    show(page, "devices")
    page.fill("#device-name", "Follow spot")
    page.fill("#device-start", "50")
    page.click("#add-channel-row")
    page.fill("#channel-rows .ch-name", "Iris")
    page.click('#device-form button[type="submit"]')
    page.wait_for_timeout(400)

    assert "Follow spot (start ch. 50)" in page.inner_text("#device-list")
    assert any(d["name"] == "Follow spot" for d in board["state"]["devices"])


# -- settings --------------------------------------------------------------


def test_settings_shows_the_saved_networks(page):
    show(page, "settings")
    text = page.inner_text("#wifi-list")

    assert "StageNet (priority 10)" in text
    assert "BackupHotspot (priority 1)" in text


def test_scanning_fills_the_ssid_suggestions(page):
    show(page, "settings")
    page.click("#wifi-scan-btn")
    page.wait_for_timeout(400)

    options = page.eval_on_selector_all(
        "#wifi-scan-results option", "nodes => nodes.map(n => n.value)"
    )
    assert "GuestWifi" in options


def test_the_mqtt_form_is_populated_from_the_board(page):
    show(page, "settings")

    assert page.input_value("#mqtt-host") == "192.168.1.20"
    assert page.input_value("#mqtt-port") == "1883"
    assert page.input_value("#mqtt-base") == "dmxwifi"
    assert page.is_checked("#mqtt-enabled")


def test_the_system_form_is_populated_from_the_board(page):
    show(page, "settings")

    assert page.input_value("#sys-tx") == "D4"
    assert page.input_value("#sys-ap-ssid") == "ESP-DMX"
    assert page.input_value("#sys-ap-ip") == "1.1.1.1"
    assert page.is_checked("#sys-dir-enable") is False


def test_saving_the_system_form_sends_it_back(page, board):
    show(page, "settings")
    page.fill("#sys-tx", "IO7")
    page.click('#system-form button[type="submit"]')
    page.wait_for_timeout(400)

    assert board["state"]["system"]["dmx_tx_pin"] == "IO7"


def test_the_mesh_section_is_marked_work_in_progress(page):
    show(page, "settings")
    assert "WIP" in page.inner_text("#view-settings")


# -- settings: static IP ---------------------------------------------------


def test_the_static_ip_form_is_populated_from_the_board(page):
    show(page, "settings")

    assert page.input_value("#staticip-mode") == "dhcp"
    assert page.input_value("#staticip-netmask") == "255.255.255.0"
    assert page.input_value("#staticip-dns") == "1.1.1.1"


def test_the_address_fields_are_greyed_out_while_on_dhcp(page):
    show(page, "settings")

    for field in ("#staticip-ip", "#staticip-netmask", "#staticip-gateway", "#staticip-dns"):
        assert page.is_disabled(field), "%s should not be editable under DHCP" % field


def test_choosing_static_enables_the_address_fields(page):
    show(page, "settings")

    page.select_option("#staticip-mode", "static")
    page.wait_for_timeout(200)

    for field in ("#staticip-ip", "#staticip-netmask", "#staticip-gateway", "#staticip-dns"):
        assert page.is_enabled(field)


def test_switching_back_to_dhcp_greys_them_out_again(page):
    show(page, "settings")
    page.select_option("#staticip-mode", "static")
    page.wait_for_timeout(150)

    page.select_option("#staticip-mode", "dhcp")
    page.wait_for_timeout(150)

    assert page.is_disabled("#staticip-ip")


def test_saving_a_static_address_sends_every_field(page, board):
    show(page, "settings")
    page.select_option("#staticip-mode", "static")
    page.fill("#staticip-ip", "192.168.1.50")
    page.fill("#staticip-netmask", "255.255.255.0")
    page.fill("#staticip-gateway", "192.168.1.1")
    page.fill("#staticip-dns", "9.9.9.9")

    page.click('#staticip-form button[type="submit"]')
    page.wait_for_timeout(400)

    system = board["state"]["system"]
    assert system["sta_ip_mode"] == "static"
    assert system["sta_static_ip"] == "192.168.1.50"
    assert system["sta_static_gateway"] == "192.168.1.1"
    assert system["sta_static_dns"] == "9.9.9.9"

    # Put it back so the shared board does not leak into later tests.
    page.select_option("#staticip-mode", "dhcp")
    page.click('#staticip-form button[type="submit"]')
    page.wait_for_timeout(300)


# -- settings: .env export -------------------------------------------------


def test_the_export_button_offers_a_download(page):
    show(page, "settings")
    link = page.query_selector('a[href="/api/export-env"]')

    assert link is not None, "the Export .env link is gone"
    assert link.get_attribute("download") == "config.env"
    assert "Export" in link.inner_text()


def test_the_export_returns_an_env_file_the_deploy_script_can_read(page):
    show(page, "settings")

    body = page.evaluate("() => fetch('/api/export-env').then(r => r.text())")

    # Key names only. Values come from a board fixture other tests write to.
    for key in (
        "WIFI_1_SSID=",
        "MQTT_HOST=",
        "MQTT_BASE_TOPIC=",
        "DMX_TX_PIN=",
        "AP_SSID=",
        "STA_IP_MODE=",
        "MESH_ROLE=",
        "DEVICE_1_NAME=",
        "DEVICE_1_CHANNEL_1_TYPE=",
    ):
        assert key in body, "%s missing from the exported .env" % key


def test_the_exported_file_downloads_under_a_sensible_name(page):
    show(page, "settings")

    with page.expect_download() as info:
        page.click('a[href="/api/export-env"]')

    assert info.value.suggested_filename == "config.env"


# -- info ------------------------------------------------------------------


def test_info_shows_the_firmware_version(page, board):
    show(page, "info")

    assert page.inner_text("#info-version").strip() == board["state"]["info"]["version"]


def test_info_links_to_the_author_and_the_repository(page):
    show(page, "info")

    assert page.get_attribute("#info-author a", "href") == "https://github.com/CestMoiRoma"
    assert "github.com" in page.get_attribute("#info-repo a", "href")


def test_info_offers_both_the_online_and_the_on_board_wiki(page):
    show(page, "info")

    hrefs = page.eval_on_selector_all("#info-wiki a", "nodes => nodes.map(n => n.href)")
    assert len(hrefs) == 2
    assert any(h.endswith("/wiki.md") for h in hrefs)
