from solders.pubkey import Pubkey

from mmkit import issuer
from mmkit.spl import ata

# a split by another participant on the fixture market:
# AiZuHpA6tTb8LBkpQQJd9nz4NfZpMZT3KPjitNbSA9tnANtcfRC2PtC86ZXqy8WGsm4xBoXbd8iWLBU7u5v7qVx
SPLIT_OWNER = Pubkey.from_string("FuNgUdjWtHTQq6mEzGjcfTcmCZWbESrBoK8ywyADV5tu")
SPLIT_DATA = "7cbd1b2bd82893422be1c20000000000"
SPLIT_KEYS = [
    "FuNgUdjWtHTQq6mEzGjcfTcmCZWbESrBoK8ywyADV5tu",
    "638vJXume9w4RMhxMUJLPgkoj8K9UhMJr2jKM8j6KWs",
    "CASHx9KJUStyftLFWGvEVf59SGeG9sh5FfcnZMVPCASH",
    "93gJ8Ct8xLUFdTu3MKttzb6KLBuE4RN9VRaHGUEmTemX",
    "7PVbdSQiuh4hHkmRBCVjRr9kUfiotc6XYzvfWxZXcm5Z",
    "CP4ViB6K3rhd8oeXfgAFQ1uccEDj5vXnKZt5A6doFQof",
    "GZEyYgkfNTYNahHbjLYf8h1W4XwXUsxpJ9GHL6j5jC1G",
    "H4fFyuPSw4KbCu6FzsMtpyXePzpyGrZcQ1LC31mCWkwc",
    "517QggrENLMwecpVeTiogMCEB3YdTaMhp3RLXanM9m59",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
]
BASE_ACCOUNT = 7  # that owner holds BTC-UP outside its ATA; we always use the ATA


def test_split_matches_mainnet(cfg):
    ix = issuer.split(cfg, SPLIT_OWNER, 12_771_627)
    assert bytes(ix.data).hex() == SPLIT_DATA
    keys = [str(a.pubkey) for a in ix.accounts]
    assert keys[:BASE_ACCOUNT] + keys[BASE_ACCOUNT + 1 :] == SPLIT_KEYS[:BASE_ACCOUNT] + SPLIT_KEYS[BASE_ACCOUNT + 1 :]
    assert ix.accounts[BASE_ACCOUNT].pubkey == ata(SPLIT_OWNER, cfg.base)
    assert [a.is_writable for a in ix.accounts] == [True] * 9 + [False] * 2
    assert [a.is_signer for a in ix.accounts] == [True] + [False] * 10


def test_merge_discriminator(cfg):
    assert bytes(issuer.merge(cfg, SPLIT_OWNER, 1).data).hex() == "948dec2fae7e456f" + "0100000000000000"


def test_ata_matches_mainnet(cfg):
    assert str(ata(SPLIT_OWNER, cfg.quote)) == SPLIT_KEYS[5]
