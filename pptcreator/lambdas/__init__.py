"""Lambdas that run from the render image.

``plan.handler``    Lambda 1: send_now rows -> decks to send; starts the Step Function
``render.handler``  Lambda 2: one deck -> .pptx in S3
``record.handler`` was removed: vw-autoreport-sendemail writes the final run status.

Lambda 3 (send) is the separate ZIP function functions/vw-autoreport-sendemail.
It sends through Microsoft Graph and resets send_now after sending.

Every module imports ``_bootstrap`` first: it prepares the environment that pycore
reads at import time.
"""
