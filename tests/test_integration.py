import os
import sys
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db import init_db, get_connection, fetch_claims_data, generate_claim_report_markdown, record_claim_to_db

def test_module_9_integration_and_analytics():
    init_db()

    # 1. Test record claim insertion with full pipeline metadata
    sample_user = {'user_id': 1, 'username': 'admin', 'full_name': 'System Admin'}
    sample_claim = {
        'claim_id': 'CLM-INTEG-999',
        'category': 'Laptop',
        'brand': 'Dell',
        'model_number': 'DEL-XPS',
        'serial_number': 'SN-INTEG-999',
        'purchase_price': 1500.0,
        'purchase_date': '2023-01-01',
        'fault_type': 'Power Failure',
        'fault_description': 'Unit fails to boot.',
        'retailer': 'Tech Store',
        'warranty_duration': 12
    }
    
    pipeline_result = {
        'final_verdict': 'Likely Valid',
        'python_model': {'prediction': 'Valid Claim', 'confidence': 0.95},
        'teachable_machine': {'prediction': 'Valid Claim', 'confidence': 0.92},
        'model_comparison': {'comparison_status': 'Strong Match', 'confidence_delta': 0.03},
        'action_required': 'Proceed with normal automated routing.'
    }

    success, msg = record_claim_to_db(sample_claim, sample_user, pipeline_result=pipeline_result)
    assert success is True, f"Failed to record claim: {msg}"

    # 2. Test analytics data fetching
    df_analytics = fetch_claims_data()
    assert not df_analytics.empty, "Analytics DataFrame is empty"
    assert 'CLM-INTEG-999' in df_analytics['claim_id'].values, "Inserted claim not found in analytics df"

    # 3. Test Markdown Report Generation
    row = df_analytics[df_analytics['claim_id'] == 'CLM-INTEG-999'].iloc[0].to_dict()
    report_md = generate_claim_report_markdown(row)
    assert "# ASSUREX CLAIM ENGINE - INDIVIDUAL CLAIM REPORT" in report_md
    assert "CLM-INTEG-999" in report_md
    assert "Dell" in report_md

    print("Module 9 (Claim Status Tracking, Search & Analytics Export) Unit Tests Passed Successfully!")

if __name__ == '__main__':
    test_module_9_integration_and_analytics()
