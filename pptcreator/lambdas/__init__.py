"""Lambda that runs from the render image.

``render.handler``  one state machine request -> .pptx in S3 -> event for send email

vw-autoreport-detect (ZIP) finds send_now rows and starts the state machine;
vw-autoreport-sendemail (ZIP) sends the report and resets send_now.

Every module imports ``_bootstrap`` first: it prepares the environment that pycore
reads at import time.
"""
