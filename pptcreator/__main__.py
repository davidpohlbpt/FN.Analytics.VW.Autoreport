"""`python -m pptcreator` runs the local CLI (same code path as the Lambda handler)."""

from pptcreator.lambda_handler import cli

if __name__ == "__main__":
    cli()
