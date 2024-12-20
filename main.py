import numpy as np
import os
import cv2
# import secrets

from time import time
from loguru import logger
# from typing import Annotated
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Depends, status, HTTPException
# from fastapi.security import HTTPBasic, HTTPBasicCredentials
from services.grounding_dino import ObjectDetectionServices
from model.object_detection_view_model import ObjectDetectionViewModel
from prometheus_client import Histogram
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_fastapi_instrumentator.metrics import Info

class ResponseModel(BaseModel):
    response_data: list

model = {}

# # Traces using jeager
# trace_provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "serving-grounding-dino"}))
# set_tracer_provider(trace_provider)

# jaeger_exporter = JaegerExporter(
#     agent_host_name="jaeger",
#     agent_port=6831, # Jaeger port, not for UI
# )
# span_processor = BatchSpanProcessor(jaeger_exporter) # Manage Jaeger
# trace_provider.add_span_processor(span_processor)

NAMESPACE = os.environ.get("METRICS_NAMESPACE", "fastapi")
SUBSYSTEM = os.environ.get("METRICS_SUBSYSTEM", "model")

instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
    inprogress_name="fastapi_inprogress",
    inprogress_labels=True
)

# ----- add metrics -----
instrumentator.add(
    metrics.request_size(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM,
    )
)
instrumentator.add(
    metrics.response_size(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM,
    )
)
instrumentator.add(
    metrics.latency(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM,
    )
)
instrumentator.add(
    metrics.requests(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM,
    )
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    model["detector"] = ObjectDetectionServices("cpu") 
    yield
    model.clear()

# FastAPI
app = FastAPI(lifespan=lifespan)
instrumentator.instrument(app).expose(app, include_in_schema=False, should_gzip=True)

@app.post("/detect", response_model=list[ObjectDetectionViewModel])
async def detectObject(prompt: str, data: UploadFile = File(...)): 
    start_time = time()

    try:
        image_bytes = await data.read()
        
        # Convert bytes data to a NumPy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        
        # Decode the image using OpenCV
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = model["detector"].predict(image, prompt)
        logger.info(f"{result}")
        elapsed_time = time() - start_time
        logger.info(f"Finished generate response: {elapsed_time:.2f} seconds")

        return result
    except Exception as error:
        logger.error(f"{error}")
        raise HTTPException(status_code=500, detail="Detection failed")