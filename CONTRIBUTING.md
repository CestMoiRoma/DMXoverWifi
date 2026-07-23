# Contributing

Contributions are welcome. The workflow is the usual GitHub one.

1. Fork the repository.
2. Create a branch for your change.
3. Run the test suite (see below). It must be green.
4. Open a pull request against `main`, describing what changed and why.

Issues and bug reports are just as useful as code, especially if you are running
this on a board other than the Lolin S2 Mini.

## Running the tests

Everything runs off the board. `test/` contains fake CircuitPython modules that
stand in for the ESP32 hardware, so the firmware can be imported and exercised on
a normal PC.

```bash
docker compose -f test/docker-compose.yml run --rm tests
```

Or without Docker, if you have Python 3.11 or newer:

```bash
pip install -r test/requirements.txt
python -m pytest test -v
```

See [WIKI.md](WIKI.md#test-suite) for what the suite covers and how the fake
hardware layer works.

## Style

Match the code around you. The firmware targets CircuitPython, so keep to what it
supports: no f-strings in `src/`, no `typing` imports, no dependencies beyond what
is already vendored in `lib/`.

Tooling under `tools/` and `test/` runs on a normal desktop Python and is free to
use the full standard library.

## Licensing

The project is under the [PolyForm Noncommercial License 1.0.0](LICENSE).

By opening a pull request you agree that your contribution is licensed under the
same terms. If you want to use this commercially, open an issue and ask.
