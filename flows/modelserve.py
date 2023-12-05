environment = "seldon"

import yaml
import prefect
from prefect import task, flow, tags, get_run_logger
from kubernetes import client, config

seldon_deployment = """
    apiVersion: machinelearning.seldon.io/v1alpha3
    kind: SeldonDeployment
    metadata:
      name: test2
      namespace: seldon
    spec:
      predictors:
      - graph:
          children: []
          implementation: MLFLOW_SERVER
          modelUri: dummy
          name: test
        name: model-a2
        replicas: 1
        traffic: 100
        componentSpecs:
        - spec:
            # We are setting high failureThreshold as installing conda dependencies
            # can take long time and we want to avoid k8s killing the container prematurely
            containers:
            - name: test22
              livenessProbe:
                initialDelaySeconds: 60
                failureThreshold: 100
                periodSeconds: 5
                successThreshold: 1
                httpGet:
                  path: /health/ping
                  port: http
                  scheme: HTTP
              readinessProbe:
                initialDelaySeconds: 60
                failureThreshold: 100
                periodSeconds: 5
                successThreshold: 1
                httpGet:
                  path: /health/ping
                  port: http
                  scheme: HTTP
"""

CUSTOM_RESOURCE_INFO = dict(
    group="machinelearning.seldon.io",
    version="v1alpha3",
    plural="seldondeployments",
)

@task
def deploy_model(model_uri: str, namespace: str = "seldon"):
    logger = get_run_logger()

    logger.info(f"Deploying model {model_uri} to enviroment {namespace}")

    config.load_incluster_config()
    custom_api = client.CustomObjectsApi()

    dep = yaml.safe_load(seldon_deployment)
    dep["spec"]["predictors"][0]["graph"]["modelUri"] = model_uri

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
def DeployModel(model_uri: str = "Train"):
      deploy_model(model_uri, namespace="seldon")
@flow    
def DeploySecondModel(model_uri: str = "Train"):
      deploy_model(model_uri, namespace="seldon")

if __name__ == "__main__":
    with tags("test1"):
        #DeployModel()
        DeploySecondModel()
