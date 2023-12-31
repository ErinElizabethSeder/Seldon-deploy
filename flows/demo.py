environment = "seldon"

import yaml
import prefect
from prefect import task, flow, tags, get_run_logger, variables
from kubernetes import client, config
import mlflow
from mlflow import MlflowClient

seldon_deployment = """
apiVersion: machinelearning.seldon.io/v1alpha3
kind: SeldonDeployment
metadata:
  name: mlflow
spec:
  name: wines
  predictors:
  - componentSpecs:
    - spec:
        protocol: v2
        # We are setting high failureThreshold as installing conda dependencies
        # can take long time and we want to avoid k8s killing the container prematurely
        containers:
        - name: classifier
          livenessProbe:
            initialDelaySeconds: 500
            failureThreshold: 500
            periodSeconds: 5
            successThreshold: 1
            httpGet:
              path: /health/ping
              port: http
              scheme: HTTP
          readinessProbe:
            initialDelaySeconds: 500
            failureThreshold: 500
            periodSeconds: 5
            successThreshold: 1
            httpGet:
              path: /health/ping
              port: http
              scheme: HTTP
    graph:
      children: []
      implementation: MLFLOW_SERVER
      modelUri: s3://mlflow/1/bea65707b313480090350c83bc95a77c/artifacts/model
      envSecretRefName: bpk-seldon-init-container-secret
#      envSecretRefName: seldon-init-container-secret
      name: classifier
    name: demo
    replicas: 1
"""

CUSTOM_RESOURCE_INFO = dict(
    group="machinelearning.seldon.io",
    version="v1alpha3",
    plural="seldondeployments",
)
@task
def get_model_location(model_name):
    mlflow.set_tracking_uri(variables.get('mlflow_tracking_uri'))
    client = MlflowClient()
    model_metadata = client.get_latest_versions(model_name)
    latest_model_location = model_metadata[0].source
    return latest_model_location
@task
def deploy_model(model_uri: str, serving_name: str, namespace: str = "seldon"):
    logger = get_run_logger()

    logger.info(f"Deploying model {model_uri} to enviroment {namespace}")

    config.load_incluster_config()
    custom_api = client.CustomObjectsApi()

    dep = yaml.safe_load(seldon_deployment)
    dep["spec"]["predictors"][0]["graph"]["modelUri"] = model_uri
    dep["metadata"]["name"] = serving_name

    try:
        resp = custom_api.create_namespaced_custom_object(
            **CUSTOM_RESOURCE_INFO,
            namespace=namespace,
            body=dep,
        )

        logger.info("Deployment created. status='%s'" % resp["status"]["state"])
    except:
        logger.info("Updating existing model")
        existing_deployment = custom_api.get_namespaced_custom_object(
            **CUSTOM_RESOURCE_INFO,
            namespace=namespace,
            name=dep["metadata"]["name"],
        )
        existing_deployment["spec"]["predictors"][0]["graph"]["modelUri"] = model_uri

        resp = custom_api.replace_namespaced_custom_object(
            **CUSTOM_RESOURCE_INFO,
            namespace=namespace,
            name=existing_deployment["metadata"]["name"],
            body=existing_deployment,
        )

@flow    
def demo_serve(model_name: str, serving_name:str):
      model_uri = get_model_location(model_name)
      deploy_model(model_uri, serving_name, namespace="seldon")
  
if __name__ == "__main__":
    with tags("demo"):
        #DeployModel()
        #DeploySecondModel()
        demo_serve()
