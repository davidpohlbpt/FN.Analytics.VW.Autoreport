"""Lambda 3: e-mail a rendered deck. Deployed as a ZIP, separate from the render image.

Only the standard library and boto3 (part of the Lambda Python runtime) are used here,
so this package must never import ``pptcreator``, pycore, python-pptx or pandas.
"""
