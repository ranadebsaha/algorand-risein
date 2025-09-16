# scripts/deploy_and_interact.py

import logging
import algokit_utils
from algokit_utils import ApplicationClient, get_creator_account

logger = logging.getLogger(__name__)

def deploy(algorand: algokit_utils.AlgorandClient) -> ApplicationClient:
    """
    Deploys the CertificateRegistry smart contract application to the Algorand network.
    Args:
        algorand: An AlgorandClient instance configured for the target network.
    Returns:
        An ApplicationClient instance for the deployed contract.
    """
    # Import the generated client for the smart contract.
    # This file is automatically created by AlgoKit after the smart contract is compiled.
    from smart_contracts.artifacts.certificate_registry.certificate_registry_client import (
        CertificateRegistryFactory,
    )

    # Get the account that will be used as the deployer and signer.
    deployer = get_creator_account(algorand)
    logger.info(f"Using deployer account: {deployer.address}")

    # Get the typed app factory for the contract.
    factory = algorand.client.get_typed_app_factory(
        CertificateRegistryFactory, default_sender=deployer
    )

    # Deploy the app.
    # on_update and on_schema_break policies are set to AppendApp
    # to allow for non-breaking changes to be appended to the contract
    # without a full redeployment.
    app_client, result = factory.deploy(
        on_update=algokit_utils.OnUpdate.AppendApp,
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
    )
    logger.info(
        f"App deployment result: {result.operation_performed} "
        f"for app with ID: {app_client.app_id}"
    )

    # Fund the application account if it's a new deployment.
    if result.operation_performed in [
        algokit_utils.OperationPerformed.Create,
        algokit_utils.OperationPerformed.Replace,
    ]:
        algorand.send.payment(
            algokit_utils.PaymentParams(
                amount=algokit_utils.AlgoAmount.Algos(1),
                sender=deployer.address,
                receiver=app_client.app_address,
            )
        )
        logger.info(f"Funded app {app_client.app_id} with 1 Algo.")

    return app_client

def run_examples(app_client: ApplicationClient):
    """
    Shows example usage of the deployed smart contract methods.
    Args:
        app_client: An ApplicationClient instance for the deployed contract.
    """
    # A sample certificate hash. In your real application, this would be computed
    # from the uploaded certificate file.
    cert_hash_example = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
    
    logger.info(f"--- Registering Certificate with hash: {cert_hash_example} ---")
    try:
        response = app_client.call("register_certificate", cert_hash=cert_hash_example)
        logger.info(
            f"Registered cert_hash: {cert_hash_example}, "
            f"transaction ID: {response.transaction.txid}"
        )
    except Exception as e:
        logger.error(f"Failed to register certificate: {e}")

    logger.info(f"\n--- Verifying Certificate with hash: {cert_hash_example} ---")
    try:
        # Note: The 'call' method is used for mutating methods (state changes).
        # For a read-only method, you can use app_client.simulate to avoid a transaction.
        # We'll use a direct call here for simplicity.
        response = app_client.call("verify_certificate", cert_hash=cert_hash_example)
        # The ABI return value is decoded for us.
        owner_address = response.return_value
        logger.info(f"Verification successful. Owner's address: {owner_address.decode('utf-8')}")
    except Exception as e:
        logger.error(f"Failed to verify certificate: {e}")

def main():
    """Main function to run deployment and examples."""
    algorand = algokit_utils.AlgorandClient.from_environment()
    app_client = deploy(algorand)
    run_examples(app_client)
    
if __name__ == "__main__":
    main()
