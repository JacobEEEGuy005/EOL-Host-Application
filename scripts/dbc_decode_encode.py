import can, cantools, sys

bus = can.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000) if any(c['interface'] == 'pcan' for c in can.detect_available_configs()) else None
db = cantools.database.load_file('docs/can_specs/eol_firmware.dbc') if bus else None

if db:
    if len(sys.argv) > 3:
        msg_name, sig_name, value_str = sys.argv[1:4]
        selected_msg = next((m for m in db.messages if m.name == msg_name), None) or exit(f"Message {msg_name} not found")
        selected_sig = next((s for s in selected_msg.signals if s.name == sig_name), None) or exit(f"Signal {sig_name} not found")
        value = float(value_str) if '.' in value_str else int(value_str)
    else:
        messages = list(db.messages)
        print("Messages:", [m.name for m in messages])
        selected_msg = messages[int(input("Index: "))]
        signals = list(selected_msg.signals)
        print("Signals:", [s.name for s in signals])
        selected_sig = signals[int(input("Index: "))]
        value = float(input(f"Value for {selected_sig.name}: ") or 0)

    mux_value = selected_sig.multiplexer_ids[0] if getattr(selected_sig, 'multiplexer_ids', None) else None
    encode_data = {sig.name: (value if sig == selected_sig else list(sig.choices.keys())[0] if getattr(sig, 'choices', None) else 0) for sig in selected_msg.signals if sig.name in ['DeviceID', 'MessageType'] or sig == selected_sig}
    if mux_value: encode_data['MessageType'] = mux_value

    bus.send(can.Message(arbitration_id=selected_msg.frame_id, data=db.encode_message(selected_msg.name, encode_data), is_extended_id=False))
    print("Sent.")
else:
    print("No bus/DBC.")

if bus: bus.shutdown()