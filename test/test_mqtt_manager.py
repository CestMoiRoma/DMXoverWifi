"""MQTT bridge: connection lifecycle, Home Assistant discovery, command handling."""
import json

from adafruit_minimqtt.adafruit_minimqtt import MQTT


def enable(mqtt, **overrides):
    cfg = {"enabled": True, "host": "broker.local"}
    cfg.update(overrides)
    mqtt.set_config(cfg)
    mqtt.start()
    return MQTT.last_instance


def discovery_for(client, entity, uid):
    topic = "homeassistant/%s/%s/config" % (entity, uid)
    matches = client.published_to(topic)
    assert matches, "no discovery config published on %s" % topic
    return json.loads(matches[-1]["payload"])


def test_disabled_mqtt_never_opens_a_connection(mqtt):
    mqtt.set_config({"enabled": False, "host": "broker.local"})
    mqtt.start()

    assert mqtt.client is None
    assert MQTT.last_instance is None


def test_enabled_without_a_broker_host_stays_offline(mqtt):
    mqtt.set_config({"enabled": True, "host": ""})
    mqtt.start()

    assert mqtt.client is None


def test_credentials_are_handed_to_the_client(mqtt):
    client = enable(mqtt, port=8883, username="dmx", password="secret")

    assert client.broker == "broker.local"
    assert client.port == 8883
    assert client.username == "dmx"
    assert client.password == "secret"
    assert mqtt.client is not None


def test_blank_credentials_are_sent_as_none(mqtt):
    client = enable(mqtt, username="", password="")

    assert client.username is None
    assert client.password is None


def test_an_unreachable_broker_does_not_take_the_board_down(mqtt):
    MQTT.fail_connect = True

    mqtt.set_config({"enabled": True, "host": "broker.local"})
    mqtt.start()

    assert mqtt.client is None
    assert mqtt.status()["connected"] is False


def test_status_reports_the_bridge_state(mqtt):
    assert mqtt.status() == {"enabled": False, "connected": False, "broker": ""}

    enable(mqtt)

    assert mqtt.status() == {"enabled": True, "connected": True, "broker": "broker.local"}


def test_config_is_persisted_across_a_reboot(mqtt):
    from src.mqtt_manager import MqttManager

    mqtt.set_config({"enabled": True, "host": "broker.local", "base_topic": "stage"})

    assert MqttManager(mqtt.device_manager).cfg["base_topic"] == "stage"


def test_stop_disconnects_and_clears_the_client(mqtt):
    client = enable(mqtt)

    mqtt.stop()

    assert mqtt.client is None
    assert client.disconnect_calls == 1


def test_sliders_are_published_as_home_assistant_numbers(mqtt, par_fixture):
    client = enable(mqtt)
    uid = "%s_1" % par_fixture.id

    payload = discovery_for(client, "number", uid)

    assert payload["name"] == "Dimmer"
    assert payload["unique_id"] == uid
    assert payload["min"] == 0
    assert payload["max"] == 255
    assert payload["step"] == 1
    assert payload["command_topic"] == "dmxwifi/%s/set" % uid
    assert payload["state_topic"] == "dmxwifi/%s/state" % uid


def test_switch_channels_are_published_as_switches(mqtt, par_fixture):
    client = enable(mqtt)
    uid = "%s_4" % par_fixture.id

    payload = discovery_for(client, "switch", uid)

    assert payload["name"] == "Lamp"
    assert payload["payload_on"] == "255"
    assert payload["payload_off"] == "0"
    assert payload["state_on"] == "255"
    assert payload["state_off"] == "0"


def test_momentary_and_trigger_channels_are_published_as_buttons(mqtt, devices):
    device = devices.add_device(
        "Fog",
        20,
        [
            {"offset": 1, "name": "Burst", "type": "button"},
            {"offset": 2, "name": "Hold", "type": "button-momentary"},
        ],
    )
    client = enable(mqtt)

    for offset, name in ((1, "Burst"), (2, "Hold")):
        payload = discovery_for(client, "button", "%s_%d" % (device.id, offset))
        assert payload["name"] == name
        # A button entity is stateless, so no state topic is advertised.
        assert "state_topic" not in payload


def test_all_channels_of_a_fixture_share_one_device_block(mqtt, par_fixture):
    client = enable(mqtt)

    blocks = [
        json.loads(p["payload"])["device"]
        for p in client.published
        if p["topic"].startswith("homeassistant/")
    ]

    assert len(blocks) == 4
    assert all(b == blocks[0] for b in blocks)
    assert blocks[0]["identifiers"] == [par_fixture.id]
    assert blocks[0]["name"] == "PAR LED"


def test_discovery_configs_are_retained(mqtt, par_fixture):
    client = enable(mqtt)

    configs = [p for p in client.published if p["topic"].startswith("homeassistant/")]
    assert configs and all(p["retain"] for p in configs)


def test_the_board_subscribes_to_every_command_topic(mqtt, par_fixture):
    client = enable(mqtt)

    assert sorted(client.subscriptions) == sorted(
        "dmxwifi/%s_%d/set" % (par_fixture.id, offset) for offset in (1, 2, 3, 4)
    )


def test_a_custom_base_topic_and_prefix_are_honoured(mqtt, par_fixture):
    client = enable(mqtt, base_topic="stage", discovery_prefix="ha")

    assert client.published_to("ha/number/%s_1/config" % par_fixture.id)
    assert "stage/%s_1/set" % par_fixture.id in client.subscriptions


def test_a_slider_command_moves_the_dmx_channel(mqtt, par_fixture, dmx):
    client = enable(mqtt)

    client.inject("dmxwifi/%s_1/set" % par_fixture.id, "128")

    assert dmx.buffer[1] == 128
    assert client.published_to("dmxwifi/%s_1/state" % par_fixture.id)[-1]["payload"] == "128"


def test_a_float_slider_payload_is_truncated(mqtt, par_fixture, dmx):
    client = enable(mqtt)

    client.inject("dmxwifi/%s_1/set" % par_fixture.id, "200.7")

    assert dmx.buffer[1] == 200


def test_a_junk_slider_payload_is_ignored(mqtt, par_fixture, dmx):
    client = enable(mqtt)

    client.inject("dmxwifi/%s_1/set" % par_fixture.id, "bright please")

    assert dmx.buffer[1] == 0


def test_a_momentary_channel_fires_full_on_whatever_the_payload(mqtt, par_fixture, dmx):
    client = enable(mqtt)

    client.inject("dmxwifi/%s_3/set" % par_fixture.id, "press")

    assert dmx.buffer[3] == 255
    # Stateless, so nothing is echoed back on the state topic.
    assert client.published_to("dmxwifi/%s_3/state" % par_fixture.id) == []


def test_a_switch_channel_understands_on_and_off(mqtt, par_fixture, dmx):
    client = enable(mqtt)
    topic = "dmxwifi/%s_4/set" % par_fixture.id

    client.inject(topic, "ON")
    assert dmx.buffer[4] == 255

    client.inject(topic, "off")
    assert dmx.buffer[4] == 0

    client.inject(topic, "255")
    assert dmx.buffer[4] == 255

    states = [p["payload"] for p in client.published_to("dmxwifi/%s_4/state" % par_fixture.id)]
    assert states == ["255", "0", "255"]


def test_an_unrecognised_switch_payload_leaves_the_channel_alone(mqtt, par_fixture, dmx):
    client = enable(mqtt)
    client.inject("dmxwifi/%s_4/set" % par_fixture.id, "ON")

    client.inject("dmxwifi/%s_4/set" % par_fixture.id, "maybe")

    assert dmx.buffer[4] == 255


def test_messages_for_unknown_topics_are_dropped(mqtt, par_fixture, dmx):
    client = enable(mqtt)

    client.inject("someone-elses/topic", "255")
    client.inject("dmxwifi/%s_1/state" % par_fixture.id, "255")
    client.inject("dmxwifi/dev-ghost_1/set", "255")
    client.inject("dmxwifi/%s_99/set" % par_fixture.id, "255")
    client.inject("dmxwifi/malformed/set", "255")

    assert set(dmx.buffer) == {0}


def test_publish_state_is_a_no_op_while_offline(mqtt, par_fixture):
    mqtt.publish_state(par_fixture.id, 1, 128)  # must not raise


def test_loop_drops_the_client_when_the_broker_goes_away(mqtt):
    client = enable(mqtt)

    def explode(timeout=0):
        raise OSError("connection reset")

    client.loop = explode
    mqtt.loop()

    assert mqtt.client is None, "a dead broker must not wedge the main loop"
