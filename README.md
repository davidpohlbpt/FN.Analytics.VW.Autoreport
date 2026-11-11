# FN.Analytics.VW.Autoreport

Automated PowerPoint reporting for VW. Builds `.pptx` decks from template slides,
pulls chart configuration and data from the Config Center (DQN) REST API, optionally
enriches it with data from the application database, stores the result in blob
storage, and e-mails it to the configured recipients.

## Pipeline

```
trigger (process hook / scheduler)
  -> graph_steer_creation_process
       for each active template
         -> graph_get_config
              - get_database_config      (control DB: templates, mappings, recipients)
              - get_template_config      (.pptx shapes: positions, fonts, legend)
              - get_config_center_config (DQN API: tiles, colors, filters, chart data)
         -> graph_create_ppt             (python-pptx rendering -> blob storage)
         -> send_email                   (MS Graph sendMail with attachment)
```

## Configuration sources

| Source | Location |
|---|---|
| Template / mapping / recipients | DB schema `control`, tables `T_CONTROL_PptCreator_*` |
| Shape positions, fonts, legend | the `.pptx` template in blob storage |
| Chart data, colors, headlines | DQN API, see `pptcreator/configs/endpoints.py` |

## Setup

1. `poetry install`
2. Copy `.env.example` to `.env` and fill in the values (never commit `.env`).
3. Run the migrations: `alembic upgrade head`
4. Run the tests: `pytest`

## Entry points

- `python -m pptcreator` -- local run with dummy load info
- `pptcreator/main_real_data_config_center.py` -- config + data fetch without rendering
- `pptcreator/main_real_data_email.py` -- e-mail dispatch only

## Notes

- Only `doughnut` charts are currently supported (see `pptcreator/models/enum.py`).
- Chart rows must be `{"category": ..., "value": ...}` dicts: `create_charts` uses the
  first key as category and the second as value, by insertion order.
- Template shapes are matched by name suffix: `"<object> Chart"`, `"<object> Headline"`,
  `"<object> Box"`, `"<object> Total"`. Keep the role keyword at the *end* of the name.
