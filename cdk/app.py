#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.vpc_stack import VPCStack
from stacks.ec2_stack import EC2Stack
from stacks.iot_stack import IoTStack
from stacks.msk_stack import MSKStack
from stacks.bedrock_stack import BedrockStack
from stacks.s3_stack import S3Stack
from stacks.rag_stack import RAGStack
from stacks.opensearch_stack import OpenSearchStack
import subprocess
import os
import sys

# Konfiguracja środowiska AWS
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION', 'eu-central-1')
)

# Flagi do kontrolowania, które stacki mają być wdrożone
                          # Długi czas wdrożenia - wysokie koszty
DEPLOY_OPENSEARCH = False # Domyślnie wyłączone
DEPLOY_RAG = False         # Dodana flaga - domyślnie RAGStack nie będzie wdrażany

DEPLOY_IOT = False        # Opcjonalnie do włączenia później


app = cdk.App()

# 1. Bazowy VPC Stack (wszystkie inne od niego zależą)
vpc_stack = VPCStack(app, "VPCStack", env=env)

# 2. MSK Stack (zależy od VPC)
msk_stack = MSKStack(app, "MSKStack", vpc=vpc_stack.vpc, env=env)
msk_stack.add_dependency(vpc_stack)

# 3. S3 Stack (zależy od VPC)
s3_stack = S3Stack(app, "S3Stack", env=env)

# 4. OpenSearch Stack (opcjonalny, zależy od VPC)
opensearch_stack = None
if DEPLOY_OPENSEARCH:
    opensearch_stack = OpenSearchStack(app, "OpenSearchStack",
        vpc=vpc_stack.vpc,
        env=env
    )
    opensearch_stack.add_dependency(vpc_stack)

# 5. Bedrock Stack (opcjonalny, wdrażany tylko gdy RAG jest włączony)
bedrock_stack = None
if DEPLOY_RAG:
    bedrock_stack = BedrockStack(app, "BedrockStack", env=env)

# 6. IoT Stack (opcjonalny, zależy od MSK)
iot_stack = None
if DEPLOY_IOT:
    iot_stack = IoTStack(app, "CoreStack", msk_stack=msk_stack, env=env)
    iot_stack.add_dependency(msk_stack)

# 7. EC2 Stack (zależy od wszystkich aktywnych stacków)
ec2_stack = EC2Stack(app, "EC2Stack",
    vpc=vpc_stack.vpc,
    msk_stack=msk_stack,
    s3_stack=s3_stack,
    iot_stack=iot_stack,                 # Może być None
    bedrock_stack=bedrock_stack,         # Może być None
    env=env
)

# Dodaj wszystkie zależności dla EC2
ec2_stack.add_dependency(vpc_stack)
ec2_stack.add_dependency(msk_stack)
ec2_stack.add_dependency(s3_stack)
if DEPLOY_IOT:
    ec2_stack.add_dependency(iot_stack)
if DEPLOY_RAG and bedrock_stack:
    ec2_stack.add_dependency(bedrock_stack)

# 8. RAG Stack (opcjonalny, zależy od S3, Bedrock i OpenSearch)
if DEPLOY_RAG:
    rag_stack = RAGStack(app, "RAGStack",
        s3_bucket=s3_stack.bucket,  # Przekazujemy bezpośrednio bucket zamiast używać eksportu
        opensearch_stack=opensearch_stack,  # Może być None
        bedrock_role_arn=bedrock_stack.bedrock_role.role_arn if bedrock_stack else None,  # Przekazujemy ARN roli
        env=env
    )
    rag_stack.add_dependency(s3_stack)
    if bedrock_stack:
        rag_stack.add_dependency(bedrock_stack)
    if DEPLOY_OPENSEARCH and opensearch_stack:
        rag_stack.add_dependency(opensearch_stack)

app.synth()

# Po syntezie, zapisz outputy i ewentualnie wylistuj stacki
script_path = os.path.join(os.path.dirname(__file__), 'scripts', 'save_outputs.py')
subprocess.run(['python', script_path])

# Dodaj opcję listowania stacków
if '--list-stacks' in sys.argv:
    list_stacks_path = os.path.join(os.path.dirname(__file__), 'scripts', 'list_stacks.py')
    subprocess.run(['python', list_stacks_path])

# Dodaj opcję planowania zmian (CDK Diff)
if '--plan' in sys.argv:
    stack_index = sys.argv.index('--plan') + 1
    stack_name = sys.argv[stack_index] if stack_index < len(sys.argv) and not sys.argv[stack_index].startswith('--') else None

    if stack_name:
        subprocess.run(['cdk', 'diff', stack_name])
    else:
        subprocess.run(['cdk', 'diff'])

    print("\nAby wdrożyć zmiany, użyj komendy 'cdk deploy'.")