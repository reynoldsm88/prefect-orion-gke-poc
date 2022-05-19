The document below details the steps required to deploy a prefect orion agent on a GKE cluster. It uses
a Google Cloud bucket storage and I demonstrate how I deploy a and run a flow that listens messages from a Confluent
Cloud topic.

I'm using python 3.8.10

```shell
python --version
```
```text
Python 3.8.10
```

Create a python virtual environment in the current directory:

```shell
python -m venv ./venv
source venv/bin/activate
pip install -r requirements.txt
```

Generate a prefect orion manifest (2.0) : 

```shell
prefect orion kubernetes-manifest > k8s-orion-agent.yaml
```

Keep the original as a copy for further reference : 
```shell
cp k8s-orion-agent.yaml k8s-orion-agent-original.yaml
```

The manifest then needs some manual editing because : 

- It is using a "default" service account in the "default" namespace.
  For production workloads we should use a dedicated and well named service account 
- The pod should then specify with which service account it runs
- The work-queue may need to be tweaked
- The API URL need to be edited
- There are missing rbac authorizations
- You may want to deploy the elements in a different namespace


Let's start by adding a dedicated service account to the manifest.
Add the following lines before the rbac objects for example.
```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prefect-orion-agent
```

Remove the orion service, it won't be needed : 

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: orion
  labels:
    app: orion
spec:
  ports:
    - port: 4200
      protocol: TCP
  selector:
    app: orion
```

Remove the `namespace: default` from the rbac objects to allow creating 
the objects in the namespace of your choice.

```yaml 
(...)
kind: RoleBinding
metadata:
  name: flow-runner-role-binding
(...)
```

In the RoleBinding, make sure the `subjects` refers to the service account `prefect-orion-agent` specified earlier.

```yaml 
(...)
subjects:
- kind: ServiceAccount
  name: prefect-orion-agent
(...)
```


Add `serviceAccountName: prefect-orion-agent` to the pod spec above the `containers` section

```yaml 
(...)
    spec:
      serviceAccountName: prefect-orion-agent
      containers:
(...)
```

Replace the `value` of the environment variable `PREFECT_API_URL` with you Prefect Cloud API URL.
And add the `PREFECT_API_KEY` environment variable. 
You should create the API key in your Prefect Cloud 2.0 account at https://beta.prefect.io/settings/api-keys.

```yaml 
(...)
        env:
          - name: PREFECT_API_URL
            value: 'https://api-beta.prefect.io/api/accounts/<account_uuid>/workspaces/<workspace_uuid>'
          - name: PREFECT_API_KEY
            value: '<prefect_cloud_2_0_api_key>'
(...)
```

At this point you can deploy the agent on your GKE cluster: 

```shell
kubectl apply -f k8s-orion-agent.yaml
```

Check its logs to make sure it is running. You should see something like :

```text
│ api Starting...                                                                                                                                                                                                                            │
│ api  ___ ___ ___ ___ ___ ___ _____    ___  ___ ___ ___  _  _                                                                                                                                                                               │
│ api | _ \ _ \ __| __| __/ __|_   _|  / _ \| _ \_ _/ _ \| \| |                                                                                                                                                                              │
│ api |  _/   / _|| _|| _| (__  | |   | (_) |   /| | (_) | .` |                                                                                                                                                                              │
│ api |_| |_|_\___|_| |___\___| |_|    \___/|_|_\___\___/|_|\_|                                                                                                                                                                              │
│ api Configure Prefect to communicate with the server with:                                                                                                                                                                                 │
│ api     prefect config set PREFECT_API_URL=http://0.0.0.0:4200/api                                                                                                                                                                         │
│ api Check out the dashboard at http://0.0.0.0:4200                                                                                                                                                                                         │
│ api INFO:     Started server process [8]                                                                                                                                                                                                   │
│ api INFO:     Waiting for application startup.                                                                                                                                                                                             │
│ api INFO:     Application startup complete.                                                                                                                                                                                                │
│ api INFO:     Uvicorn running on http://0.0.0.0:4200 (Press CTRL+C to quit)                                                                                                                                                                │
│ agent Starting agent connected to https://api-beta.prefect.io/api/accounts/8f6464fb-3d                                                                                                                                                     │
│ agent 6b-4fc0-8d89-107cafbf6a23/workspaces/77a268cd-2363-43dd-9de1-cc2afde567e0...                                                                                                                                                         │
│ agent   ___ ___ ___ ___ ___ ___ _____     _   ___ ___ _  _ _____                                                                                                                                                                           │
│ agent  | _ \ _ \ __| __| __/ __|_   _|   /_\ / __| __| \| |_   _|                                                                                                                                                                          │
│ agent  |  _/   / _|| _|| _| (__  | |    / _ \ (_ | _|| .` | | |                                                                                                                                                                            │
│ agent  |_| |_|_\___|_| |___\___| |_|   /_/ \_\___|___|_|\_| |_|                                                                                                                                                                            │
│ agent Agent started! Looking for work from queue 'kubernetes'... 
```


Next, on your Google Cloud project, you have to : 
- Create a GCS bucket (here gs://prefect-poc)
- Create a service account for the prefect agent
- Give the Storage Admin role on the bucket to the service account
- Create a service account key and save it to a file `sa.json` for later

Next, on Confluent Cloud, you have to : 
- Create a cluster
- Create a topic `prefect-poc`
- Create a service account
- Create an API key pair
- Create an ACL to allow the service account to read/write to the topic `prefect-poc`

If you already have a Kafka Cluster, you can also just use that one instead.

Next, since we are using a the python module `confluent-kafka` 
we will need a custom Docker image to run our flow on GKE.

You will need the following `Dockerfile`: 

``` 
FROM prefecthq/prefect:2.0b4-python3.8
COPY requirements.txt .
RUN pip install -r requirements.txt
``` 

and `requirements.txt`:
``` 
prefect==2.0b4
confluent-kafka
``` 

Build, tag and push the resulting docker image to Google Cloud Registry in your GCP project.
The commands might look like : 
```
PROJECT_NAME="prefect-poc"
REGISTRY_USER="xxxxx"
REGISTRY_PASSWORD="xxxxx"
GCP_PROJECT_ID="xxxxxx"
REGISTRY="gcr.io"
REGISTRY_IMAGE="gcr.io/${GCP_PROJECT_ID}/${PROJECT_NAME}"
REGISTRY_IMAGE_TAG=latest
docker login -u "${REGISTRY_USER}" -p "${REGISTRY_PASSWORD}" "${REGISTRY}"
docker build . -t "${REGISTRY_IMAGE}:${REGISTRY_IMAGE_TAG}"
docker push "${REGISTRY_IMAGE}:${REGISTRY_IMAGE_TAG}"
```


Next, let's prepare our actual prefect flow in the `prefect_2_kafka_kub.py`.
It implements a kafka consumer loop wrapped in a flow and starts a task for every received message. 

In the file you will have to edit the config object to fill-in:
- `bootstrap.servers` : URL for kafka
- `sasl.username` : API key for kafka
- `sasl.password` : API secret for kafka

```python
    conf = {
        'bootstrap.servers': "xxxxx",
        'group.id': "prefect_poc_kafka",
        'auto.offset.reset': 'earliest',
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'PLAIN',
        'sasl.username' :'xxxxx',
        'sasl.password': 'xxxxx'
    }
```

Next, in the DeploymentSpec, fill-in : 
- `bucket` : name of the GCP bucket
- `image` : name and tag of the docker image published earlier to execute the flow
- `namespace` : namespace in GKE to execute the flow job
- `service_account_name` : name of the kubernetes service account create in the manifest

```
DeploymentSpec(
    name="gcs",
    flow=main,
    tags=["kubernetes"],
    flow_storage=GoogleCloudStorageBlock(
        bucket="prefect-poc"
    ),
    flow_runner=KubernetesFlowRunner(
        image="gcr.io/xxxxx/prefect-poc/development:latest",
        namespace="default",
        service_account_name="prefect-orion-agent"
    ),
)
```

Next, authenticate to prefect cloud using the CLI : 
```shell
prefect cloud login --key xxxxxxx
```


Next, create the deployment using the GCS service account key : 

```shell
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/sa.json"
prefect deployment create prefect_2_kafka_kub.py
```

Run the deployment : 
```
prefect deployment run prefect_2_kafka_kub/gcs
```

You should see in the prefect agent logs that it is starting a flow.
The flow will be a kubernetes job in the namespace you have chosen.
YOu can try to publish kafka message to the `prefect-poc` topic, it should then launch prefect tasks.
