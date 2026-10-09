import sys

import boto3
import flask
import graphene
import moto


def test_python_version():
    assert sys.version_info[:2] == (3, 6)


def test_flask_version():
    assert flask.__version__ == "1.0.2"


def test_graphene_version():
    assert graphene.VERSION[:3] == (2, 1, 3)


def test_boto3_version():
    assert boto3.__version__ == "1.9.57"


def test_moto_version():
    assert moto.__version__ == "1.3.7"


def test_azure_compute_imports():
    import azure.mgmt.compute

    assert hasattr(azure.mgmt.compute, "ComputeManagementClient")
