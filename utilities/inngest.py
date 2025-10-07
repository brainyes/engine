import logging

import inngest

client = inngest.Inngest(
    app_id="brainyes",
    logger=logging.getLogger("uvicorn"),
)
