import json
from typing import List

from anyio import create_task_group, sleep
from fastapi.testclient import TestClient

from h_server import models
from h_server.contracts import Contracts
from h_server.models.task import PoseConfig, TaskConfig
from h_server.node_manager import NodeManager
from h_server.relay import Relay
from h_server.utils import get_task_hash


async def test_get_task_stats_empty(client: TestClient):
    resp = client.get("/manager/v1/tasks")
    resp.raise_for_status()
    resp_data = resp.json()
    assert resp_data["status"] == "stopped"
    assert resp_data["num_today"] == 0
    assert resp_data["num_total"] == 0


async def start_nodes(
    managers: List[NodeManager],
):
    waits = []
    for m in managers:
        assert m._node_state_manager is not None
        waits.append(await m._node_state_manager.start())
    async with create_task_group() as tg:
        for w in waits:
            tg.start_soon(w)


async def create_task(
    node_contracts: List[Contracts],
    relay: Relay,
    tx_option,
):
    prompt = ("best quality, ultra high res, photorealistic++++, 1girl, off-shoulder sweater, smiling, "
              "faded ash gray messy bun hair+, border light, depth of field, looking at "
              "viewer, closeup")

    negative_prompt = ("paintings, sketches, worst quality+++++, low quality+++++, normal quality+++++, lowres, "
                       "normal quality, monochrome++, grayscale++, skin spots, acnes, skin blemishes, "
                       "age spot, glans")

    args = {
        "base_model": "runwayml/stable-diffusion-v1-5",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "task_config": {
            "num_images": 9,
            "safety_checker": False
        }
    }
    task_args = json.dumps(args)

    task_hash = get_task_hash(task_args)
    data_hash = bytes([0]*32)

    task_id = 1
    await relay.create_task(task_id=task_id, task_args=task_args)
    waiter = await node_contracts[0].task_contract.create_task(
        task_hash=task_hash, data_hash=data_hash, option=tx_option
    )
    await waiter.wait()
    return task_id


async def test_upload_task_result(
    running_client: TestClient, node_contracts, managers, relay, tx_option
):
    await start_nodes(managers=managers)
    task_id = await create_task(node_contracts=node_contracts, relay=relay, tx_option=tx_option)
    await sleep(1)

    result_file = "test.png"
    result_hash = "0x0102030405060708"
    data = {
        "hashes": [result_hash],
    }
    with open(result_file, "rb") as f:
        files = (("files", (result_file, f, "image/png")),)
        resp = running_client.post(
            f"/manager/v1/tasks/{task_id}/result", data=data, files=files
        )
        resp.raise_for_status()
        resp_data = resp.json()
        assert resp_data["success"]


async def test_get_task_stats(
    running_client: TestClient, node_contracts, managers, relay, tx_option
):
    resp = running_client.get("/manager/v1/tasks")
    resp.raise_for_status()
    resp_data = resp.json()
    assert resp_data["status"] == "stopped"
    assert resp_data["num_today"] == 0
    assert resp_data["num_total"] == 0

    await start_nodes(managers=managers)
    resp = running_client.get("/manager/v1/tasks")
    resp.raise_for_status()
    resp_data = resp.json()
    assert resp_data["status"] == "idle"
    assert resp_data["num_today"] == 0
    assert resp_data["num_total"] == 0

    await create_task(node_contracts=node_contracts, relay=relay, tx_option=tx_option)
    await sleep(1)

    resp = running_client.get("/manager/v1/tasks")
    resp.raise_for_status()
    resp_data = resp.json()
    assert resp_data["status"] == "running"
    assert resp_data["num_today"] == 0
    assert resp_data["num_total"] == 0
