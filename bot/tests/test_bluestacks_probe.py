from bridge.diagnostics.bluestacks_probe import parse_ui_xml


def test_parse_ui_xml_preserves_visible_data_and_relationships():
    nodes = parse_ui_xml(
        '<?xml version="1.0"?><hierarchy><node class="Root" text="" content-desc="" '
        'resource-id="root" clickable="false" focusable="false" scrollable="true" enabled="true" bounds="[0,0][1,1]">'
        '<node class="TextView" text="Alice" content-desc="sender" resource-id="sender_id" clickable="true" focusable="true" scrollable="false" enabled="true" bounds="[0,0][1,1]"/>'
        '</node></hierarchy>'
    )
    assert len(nodes) == 2
    assert nodes[0]["child_ids"] == [1]
    assert nodes[1]["parent_id"] == 0
    assert nodes[1]["text"] == "Alice"
    assert nodes[1]["resource_id"] == "sender_id"
