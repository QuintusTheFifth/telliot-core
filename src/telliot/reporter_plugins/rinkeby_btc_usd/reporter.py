""" BTCUSD Price Reporter

Example of a subclassed Reporter.
"""
import asyncio
import json
import os
from typing import Any

import requests
import yaml
from telliot.reporter_base import Reporter
from telliot.reporter_plugins.rinkeby_btc_usd.abi import tellorX_playground_abi
from telliot.reporter_plugins.rinkeby_btc_usd.registry import btc_usd_data_feeds
from telliot.submitter.submitter_base import Submitter
from telliot.utils.app import default_homedir
from web3 import Web3


config = yaml.safe_load(open(os.path.join(default_homedir(), "config.yml")))


class RinkebySubmitter(Submitter):
    """Submits BTC on testnet.

    Submits BTC price data in USD to the TellorX playground
    on the Rinkeby test network."""

    def __init__(self) -> None:
        """Reads user private key and node endpoint from `.env` file to
        set up `Web3` client for interacting with the TellorX playground
        smart contract."""

        self.w3 = Web3(Web3.HTTPProvider(config["node_url"]))

        self.acc = self.w3.eth.account.from_key(config["private_key"])

        self.playground = self.w3.eth.contract(
            "0xd313B61C5Ae9cE94985177AC456a077DfE0D7A38", abi=tellorX_playground_abi
        )

    def tobytes32(self, request_id: str) -> bytes:
        """Casts request_id as bytes32."""
        return bytes(request_id, "ascii")

    def tobytes(self, value: int) -> Any:
        """Casts value as a bytes array."""
        return Web3.toBytes(hexstr=Web3.toHex(text=str(value)))

    def build_tx(self, value: float, request_id: str, gas_price: str) -> Any:
        """Assembles needed transaction data."""

        request_id_bytes = self.tobytes32(request_id)
        value_bytes = self.tobytes(int(value * 1e6))
        nonce = self.playground.functions.getNewValueCountbyRequestId(
            request_id_bytes
        ).call()

        print("nonce:", nonce)

        acc_nonce = self.w3.eth.get_transaction_count(self.acc.address)

        transaction = self.playground.functions.submitValue(
            request_id_bytes, value_bytes, nonce
        )

        estimated_gas = transaction.estimateGas()
        print("estimated gas:", estimated_gas)

        built_tx = transaction.buildTransaction(
            {
                "nonce": acc_nonce,
                "gas": estimated_gas,
                "gasPrice": self.w3.toWei(gas_price, "gwei"),
                "chainId": 4,  # rinkeby
            }
        )

        return built_tx

    def submit_data(self, value: float, request_id: str) -> Any:
        """Submits data on-chain & provides a link to view the
        successful transaction."""

        req = requests.get("https://ethgasstation.info/json/ethgasAPI.json")
        prices = json.loads(req.content)
        gas_price = str(prices["fast"])
        print("retrieved gas price:", gas_price)

        tx = self.build_tx(value, request_id, gas_price)

        tx_signed = self.acc.sign_transaction(tx)

        tx_hash = self.w3.eth.send_raw_transaction(tx_signed.rawTransaction)

        _ = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=360)
        print(f"View reported data: https://rinkeby.etherscan.io/tx/{tx_hash.hex()}")


class BTCUSDReporter(Reporter):
    """Submits the price of BTC to the TellorX playground
    every 10 seconds."""

    def __init__(self) -> None:
        self.homedir = default_homedir()
        print("homedir:", self.homedir)
        self.submitter = RinkebySubmitter()
        self.datafeeds = btc_usd_data_feeds

    async def report(self) -> None:
        """Update all off-chain values (BTC/USD) & store those values locally."""
        """Submit latest BTC/USD values to the Tellor oracle."""

        while True:
            jobs = []
            for datafeed in self.datafeeds.values():
                job = asyncio.create_task(datafeed.update_value(store=True))
                jobs.append(job)

            _ = await asyncio.gather(*jobs)

            for uid, datafeed in self.datafeeds.items():
                if datafeed.value:
                    print(f"Submitting value for {uid}: {datafeed.value.val}")
                    self.submitter.submit_data(datafeed.value.val, datafeed.request_id)
                else:
                    print(f"Skipping submission for {uid}, datafeed value not updated")

            await asyncio.sleep(10)

    def run(self) -> None:  # type: ignore
        """Used by telliot CLI to update & submit BTC/USD price data to Tellor Oracle."""

        # Create coroutines to run concurrently.
        loop = asyncio.get_event_loop()
        _ = loop.create_task(self.report())

        # Blocking loop.
        try:
            loop.run_forever()
        except (KeyboardInterrupt, SystemExit):
            loop.close()


btc_usd_reporter = BTCUSDReporter()
