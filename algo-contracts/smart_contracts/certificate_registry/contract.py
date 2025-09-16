# smart_contracts/certificate_registry/contract.py

from algopy import (
    ARC4Contract,
    BoxMap,
    Bytes,
    Global,
    Txn,
    arc4, 
)

class CertificateRegistry(ARC4Contract):
    """
    A smart contract for registering and verifying certificate hashes on the Algorand blockchain.
    It uses Algorand's Box storage to map a certificate's hash to its owner's address.
    """

    def __init__(self) -> None:
        self.certificates = BoxMap(Bytes, Bytes)

    @arc4.abimethod
    def register_certificate(self, cert_hash: Bytes) -> None:
        """
        Registers a new certificate hash and associates it with the transaction sender.
        Args:
            cert_hash: The SHA-256 hash of the certificate file.
        """
        existing_owner = self.certificates.get(cert_hash, default=Bytes(b""))
        
        # Use the lowercase 'assert' keyword
        assert existing_owner == Bytes(b""), "Certificate hash is already registered."

        self.certificates[cert_hash] = Txn.sender.bytes

    @arc4.abimethod
    def verify_certificate(self, cert_hash: Bytes) -> Bytes:
        """
        Verifies if a given certificate hash is registered and returns the owner's address.
        Args:
            cert_hash: The SHA-256 hash of the certificate to verify.
        Returns:
            The owner's address as Bytes if found, otherwise an empty Bytes string.
        """
        owner = self.certificates.get(cert_hash, default=Bytes(b""))
        return owner

    @arc4.abimethod
    def transfer_certificate(self, cert_hash: Bytes, new_owner: Bytes) -> None:
        """
        Transfers ownership of a certificate to a new address.
        This can only be called by the current owner of the certificate.
        Args:
            cert_hash: The hash of the certificate to transfer.
            new_owner: The Algorand address of the new owner.
        """
        current_owner = self.certificates.get(cert_hash, default=Bytes(b""))

        # Use the lowercase 'assert' keyword
        assert current_owner != Bytes(b""), "Certificate not found or not registered."

        # Use the lowercase 'assert' keyword
        assert current_owner == Txn.sender.bytes, "Permission denied: Only the current owner can transfer."

        self.certificates[cert_hash] = new_owner
