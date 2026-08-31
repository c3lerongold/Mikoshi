from ingestion.parsers import extract_text

def test_txt_import():
    assert extract_text("notes.txt", "olá Mikoshi".encode()) == "olá Mikoshi"

def test_json_import():
    result = extract_text("export.json", b'{"name":"Ana","likes":["jazz"]}')
    assert "Ana" in result and "jazz" in result
