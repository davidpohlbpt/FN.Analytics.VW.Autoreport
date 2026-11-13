"""One module per Lambda of the state machine (see deployment/state_machine.asl.json).

``plan.handler``    Lambda 1: control tables -> list of decks (ReportRequest + template snapshot)
``render.handler``  Lambda 2: one deck -> .pptx in S3
``send.handler``    Lambda 3: .pptx in S3 -> SES e-mail

Every module imports ``_bootstrap`` first: it prepares the environment that pycore
reads at import time.
"""
