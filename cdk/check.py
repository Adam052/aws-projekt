# check_classes.py
import aws_cdk.aws_bedrock as bedrock

# Wyświetl wszystkie dostępne klasy i metody w CfnKnowledgeBase
print("CfnKnowledgeBase properties:")
for item in dir(bedrock.CfnKnowledgeBase):
    if not item.startswith('_'):
        print(f"  - {item}")

# Wyświetl wszystkie dostępne klasy i metody w CfnKnowledgeBase.StorageConfigurationProperty
print("\nStorageConfigurationProperty properties:")
for item in dir(bedrock.CfnKnowledgeBase.StorageConfigurationProperty):
    if not item.startswith('_'):
        print(f"  - {item}")