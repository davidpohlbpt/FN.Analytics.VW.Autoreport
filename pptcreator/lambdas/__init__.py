"""Lambdas of the state machine that run from the render image (see deployment/state_machine.asl.json).

``plan.handler``    Lambda 1: control tables -> list of decks (ReportRequest + template snapshot)
``render.handler``  Lambda 2: one deck -> .pptx in S3
``record.handler``  Lambda 4: outcomes of all decks -> run log (after the Map)

Lambda 3 (send) is deployed separately as a ZIP without pycore: functions/send/sender.

Every module imports ``_bootstrap`` first: it prepares the environment that pycore
reads at import time.
"""
