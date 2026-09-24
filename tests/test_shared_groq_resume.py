import json
import tempfile
from pathlib import Path

from core.groq_config import get_groq_key, save_groq_key
from core.matcher import ResumeMatcher
from core.outreach.resume_picker import ResumePicker


def test_one_shared_groq_key_retains_other_provider_entries():
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory)
        (config / 'settings.json').write_text(json.dumps({
            'api_keys_list': [
                {'provider': 'Groq', 'name': 'old', 'key': 'gsk_old'},
                {'provider': 'Gemini', 'name': 'other', 'key': 'gemini_test'},
            ],
            'groq_api_key': 'gsk_old',
        }))
        (config / 'outreach_settings.json').write_text(json.dumps({'groq_api_key': 'gsk_legacy'}))
        assert get_groq_key(config) == 'gsk_old'
        save_groq_key('gsk_new', config)
        assert get_groq_key(config) == 'gsk_new'
        saved = json.loads((config / 'settings.json').read_text())
        assert [x['key'] for x in saved['api_keys_list'] if x['provider'] == 'Groq'] == ['gsk_new']
        assert any(x['provider'] == 'Gemini' for x in saved['api_keys_list'])
        assert not saved.get('groq_api_key')


def test_dice_and_nvoids_matcher_favors_job_occupation_over_keyword_volume():
    profiles = [
        {'id': 'analyst', 'name': 'Senior BA Analyst/ Data Analyst',
         'keywords': ['python', 'etl', 'sql', 'cloud', 'data', 'warehouse', 'aws', 'spark'],
         'unique_keywords': ['etl']},
        {'id': 'engineer', 'name': 'AWS Data Engineer',
         'keywords': ['python', 'aws'], 'unique_keywords': ['etl']},
    ]
    job = 'Senior ETL Data Engineer\nPython ETL SQL cloud warehouse AWS Spark'
    ranked = ResumeMatcher(profiles).score_profiles(job, job_title='Senior ETL Data Engineer')
    assert ranked and ranked[0]['id'] == 'engineer'
    picker = ResumePicker(profiles, semantic_enabled=False, minimum_ats_fit=0)
    assert picker.pick_resume('Senior ETL Data Engineer', job)['id'] == 'engineer'


def test_generic_job_does_not_force_specialized_exact_boost():
    profiles = [
        {'id': 'aws', 'name': 'AWS Data Engineer', 'keywords': ['aws'], 'boost_mode': 'exact'},
        {'id': 'azure', 'name': 'Azure Data Engineer', 'keywords': ['azure'], 'boost_mode': 'exact'},
    ]
    ranked = ResumeMatcher(profiles).score_profiles(
        'Data Engineer\nBuild Azure data pipelines and Azure Data Factory.',
        job_title='Data Engineer')
    assert ranked and ranked[0]['id'] == 'azure'
    assert all(result['name_boost'] < 9999 for result in ranked)


def test_devops_role_is_considered_without_unrelated_ai_engineer_profiles():
    profiles = [
        {'id': 'ai', 'name': 'Senior AI/ML Engineer', 'keywords': ['ai', 'python', 'aws']},
        {'id': 'devops', 'name': 'Senior AI/ML DevOps Engineer', 'keywords': ['aws', 'docker', 'kubernetes']},
    ]
    ranked = ResumeMatcher(profiles).score_profiles(
        'DevOps Engineer AI & Cloud\nAWS Docker Kubernetes CI/CD',
        job_title='DevOps Engineer AI & Cloud')
    assert ranked and ranked[0]['id'] == 'devops'
