# Tracing-the-Source-Demo
For hackathon GENESIS 2.0 in VESIT

https://tracing-the-source-demo-gbqckthahapps6dfzquix5f.streamlit.app/

## Run locally

```
pip install -r requirements.txt
python -m streamlit run app.py
```

Use the Light / Dark button in the top bar to switch themes.

## Tests

```
python -m pytest
```

The tests in `tests/` check that the ranking only uses reports up to the selected day,
that future reports cannot change past rankings, that the planted source is ranked first
from Day 1, and that it beats the raw case-count baseline.
