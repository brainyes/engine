import inngest

from utilities.inngest import client as inngest_client
from utilities.supabase_utilities import save_insight_type

PARAMETERS = {
    "nifti_id": "27c1ae7e-184e-4fd5-989b-b193003d3de2", # example
    "user_id": "d480e950-fb57-4ad8-9797-17e5aa8fc1cf", # example
}
INSIGHT_NAME = "my-insight-name-1"
save_insight_type(INSIGHT_NAME)

def main(**parameters):
    print("PARAMETERS: ", PARAMETERS)
    if not parameters:
        parameters = PARAMETERS
    # Use `parameters`

    ########## PAPER STARTS ##########


    ########## PAPER ENDS ##########
    return


@inngest_client.create_function(
    fn_id="insights/" + INSIGHT_NAME,
    trigger=inngest.TriggerEvent(event=INSIGHT_NAME),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    return main(**parameters)

# example:
if __name__=="__main__":
    main()
