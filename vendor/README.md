# Vendored packages

`pycore-1.0.0-py3-none-any.whl` is the internal Factory Navigator `pycore` framework
(git `FN.Analytics.PyCore`, commit `82c3083`, built with `pycore[azure,webapi]` extras
resolved in `requirements-docker.txt`). It is committed so that the Lambda image can be
built without access to Azure DevOps.

To refresh after a pycore update:

```powershell
poetry update pycore
$src = Join-Path (poetry env info -p) "src\FN.Analytics.PyCore"
poetry run python -m pip install build
poetry run python -m build --wheel --outdir vendor $src
Remove-Item vendor\pycore-*.whl -Exclude (Get-ChildItem vendor\pycore-*.whl | Sort-Object LastWriteTime | Select-Object -Last 1).Name
```

Then regenerate `requirements-docker.txt` (see README "Deployment") and rebuild the image.
