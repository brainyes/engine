import logging

import inngest

client = inngest.Inngest(
    app_id="cerebro",
    logger=logging.getLogger("uvicorn"),
)
