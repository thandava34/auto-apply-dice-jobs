# Test suite

Run the complete deterministic, offline check with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

On macOS/Linux, run `./scripts/test.sh`. To run pytest only, use
`python -m pytest -q` from the activated virtual environment.

Or, without pytest:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

The root-level `test_*.py` files are legacy/manual diagnostics. Several open a
real browser or expect machine-specific resume paths, so `pytest.ini` excludes
them from automated discovery. Live Dice or email-provider tests must be run
manually with test accounts and draft mode enabled.
