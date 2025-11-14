"""
Delete corrupt roi_volumes rows

These are 63 scans from 2025-10-11 with v1_geometric processing that have:
- Exactly 48 ROIs labeled as 'hcpex' (should be harvard-oxford)
- Labels stored as '7.0' instead of '7'
- No correct harvard-oxford data

Total rows to delete: 3,024
"""

from utilities.data import supabase

corrupt_ids = [
    '6f502b58-22bb-4bbd-872a-0ebfafac8ee8',
    'cdb64dd7-4f66-4376-97d2-fda2566cacd5',
    'e65adca1-d452-46da-bc83-bee18e01834c',
    '35952f43-baee-4765-8b3d-fe672683e2a8',
    'ba487f46-72f1-4644-ba5c-3b98e71c0ac5',
    '03622758-fcd5-450d-96b3-5a2f9f6b4d1a',
    '58582910-e782-42d4-9111-487aa2904908',
    '1fb16d1a-a579-49d9-8457-62fbc7a079a7',
    'f0921763-aef5-47c5-8c55-288668a34145',
    '88a3ef94-9b7d-46ef-970d-c0d5c564925b',
    '3e6febd8-5ded-488e-917d-641bfda3436e',
    'f410d1e4-2920-4d8f-a163-b22b5a598c02',
    'bc9bff4b-9c01-405e-a408-2d4b782ad8c1',
    'c203a707-cd47-4fdc-acc1-813c7892b63a',
    'e7ff1841-08ae-4863-8e58-cb3a75839b47',
    '7bdc5b9d-56d9-48c7-a681-24da95f170cd',
    'b97fae46-065b-4982-b65a-146ab9efd637',
    'e7b53493-d42a-4420-8965-a17db7ff134d',
    'a925cd64-e879-494d-b264-6dc22f36f5b2',
    '73904fd8-5424-4cc9-b33b-629f4ee55433',
    '480f0421-63b2-41ad-916a-bde73f6cdd82',
    '336f0c32-6554-4bf0-8333-0884fa7d5d2f',
    'e0506a99-8c5d-413e-9626-9cb4cf430203',
    '0433b90b-1746-4efd-99a5-5775b7a51475',
    '1d4bb9b4-d348-419d-ac1c-93a678e77797',
    '59c143cc-81b8-4bc3-b904-692603f6f9c2',
    '6bf45319-d447-446d-86b2-12ac739e61a4',
    '7d4269c1-b48b-400b-b0ca-97c15c2ae398',
    '2f03ccac-621a-4800-b017-923461cdc72d',
    '98205c99-e05b-4575-852f-6cb481b841ca',
    '5b38077b-8a1e-4929-93ee-9db8b2895479',
    '5acf0cfe-ee86-4013-89d6-3503f59f95eb',
    '60ea5592-4b8f-4ad5-af5a-2bd14c62c31e',
    'b3b22dcb-8d6c-48ec-9213-148459741efa',
    'f1c207f0-85f3-4945-907a-8df775611414',
    'dd2cedc2-a137-42aa-b381-db753cab9314',
    '334d48de-f882-484d-b82f-1b16bf832d27',
    '547ba7cd-48c7-4bd5-824e-8e1039d5c9d3',
    'dfc9cf8c-b4d8-4d58-8e23-63c30821fdc2',
    'e1428652-3437-41ff-b712-b7493783cb8b',
    '1b627a99-bdcf-4c59-909f-a7945ae66d0b',
    'e12dfb52-6dbf-4bad-9a12-b1ca4b0b88f8',
    '65a3899d-f1d6-494d-82ba-25081d9d0339',
    'be357a1e-4fd7-449c-9899-758104e08fb3',
    '8e144874-6d22-43a6-82cd-a794559cfae2',
    'e92271e3-b92b-4224-a9b8-300c37c80189',
    'a856b945-a0c5-4001-b373-2e2ac121ceb7',
    'cf6d562b-9c5b-4ede-9cce-ad97779ce679',
    'b75f35b8-be5c-43ea-ae19-85023b1685f2',
    'c4676f92-5b8e-4867-938d-9f84aa727b6d',
    'c3654202-f08b-4a0e-bf6d-37505c2c7ad6',
    '6fba5e55-e09e-4d08-8dcc-bc125078c5f5',
    'e2ea30f5-af55-494a-b0dc-22afe18ef33c',
    'f7c2ade2-79aa-4d03-a90d-2c5a7781fa7b',
    'efceed99-92d2-49af-9103-43a47b8f7c5a',
    '31183960-2e80-4e25-977e-2cb86a8c1f03',
    '42654275-6ed4-4036-b454-7e552e0a2153',
    'e1e9e09f-011f-44b7-aacb-06e88ad1ce85',
    '822a739e-4a7e-4da0-993b-96aa5c38f772',
    '86e13549-568f-4950-b9e3-72d77d4f4a2c',
    'c91ee2cc-20c4-4c50-b915-d067cd5bfbfe',
    '685d2657-11b0-4a51-b197-74d254716055',
    '0904500a-f461-4fc3-94cd-a98660e0166c',
]

print(f"=== DELETING CORRUPT ROI_VOLUMES DATA ===")
print(f"Total scans to clean: {len(corrupt_ids)}")
print(f"Expected rows to delete: ~{len(corrupt_ids) * 48} (63 scans × 48 ROIs)\n")

# Delete in batches of 20 scans to avoid overwhelming the API
batch_size = 20
total_deleted = 0

for i in range(0, len(corrupt_ids), batch_size):
    batch = corrupt_ids[i:i+batch_size]
    batch_num = i//batch_size + 1
    total_batches = (len(corrupt_ids) + batch_size - 1) // batch_size

    print(f"Deleting batch {batch_num}/{total_batches} ({len(batch)} scans)... ", end='', flush=True)

    try:
        result = supabase.table('roi_volumes')\
            .delete()\
            .eq('atlas_name', 'hcpex')\
            .in_('nifti_file_id', batch)\
            .execute()

        # Count deleted rows (estimate)
        deleted_count = len(batch) * 48
        total_deleted += deleted_count
        print(f"✓ (~{deleted_count} rows)")

    except Exception as e:
        print(f"✗ Error: {e}")
        break

print(f"\n✅ Deletion complete!")
print(f"Total rows deleted: ~{total_deleted}")
print(f"\nNext steps:")
print(f"1. Re-run compute_population_norms to rebuild normative data without corrupted scans")
print(f"2. The 63 scans should be reprocessed with correct pipeline to get harvard-oxford data")