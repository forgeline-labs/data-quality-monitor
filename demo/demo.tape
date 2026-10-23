Output demo/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 1000
Set Height 600
Set Padding 20

Type "./app --version"
Enter
Sleep 500ms

Type "./app validate --schema tests/fixtures/ac1_schema.json tests/fixtures/ac1.csv"
Enter
Sleep 1s

Type "./app analyze --schema tests/fixtures/ac1_schema.json tests/fixtures/ac1.csv"
Enter
Sleep 2s

Type "./app report --schema tests/fixtures/ac1_schema.json --out - --now 2026-10-06T12:00:00Z tests/fixtures/ac1.csv | head -20"
Enter
Sleep 2s
