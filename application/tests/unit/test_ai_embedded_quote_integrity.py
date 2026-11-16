"""Offline action-text integrity regressions; no HTTP, model or database."""
from pathlib import Path

import pytest

from app.p2.ai_analysis import validate_action_semantics, validate_saved_semantics


USAGE = {'commercial': False, 'modified': True, 'distributed': False,
         'network_service': True, 'training': False,
         'redistributed_assets': False, 'source_disclosure': True}
LICENSE = (Path(__file__).parents[1] / 'fixtures/official-http-server/LICENSE').read_text()
# Actual generation 06, retained verbatim from the saved preview response.
BAD_ACTION = "核对计划公开的修改后源码，依据许可条款确认版权和许可声明是否在所有副本或实质部分中保留，具体包括在源码文件的头部或尾部明确保留以下内容：'Copyright (c) 2011-2026 Charlie Robbins, Marak Squires, Jade Michael Thornton and the Contributors.' 和 'Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentationfiles"


@pytest.mark.parametrize('reader', ['new', 'saved'])
def test_actual_incomplete_embedded_english_quote_is_rejected(reader):
    assert len(BAD_ACTION) == 300
    with pytest.raises(ValueError, match='incomplete embedded quote'):
        if reader == 'new':
            validate_action_semantics(BAD_ACTION, USAGE, [])
        else:
            validate_saved_semantics({'status': 'succeeded', 'usage': USAGE,
                                      'actions': [{'text': BAD_ACTION}], 'changes': []}, USAGE)


@pytest.mark.parametrize('opener,closer', [("'", "'"), ('"', '"'), ('“', '”'), ('‘', '’')])
def test_exact_complete_copyright_quote_is_retained(opener, closer):
    quote = LICENSE.splitlines()[0]
    text = f'核对拟公开文件并保留原文：{opener}{quote}{closer}；记录其对应文件范围。'
    validate_action_semantics(text, USAGE, [])


@pytest.mark.parametrize('text', [
    '核对实际交付文件的版权与许可声明，并保留逐项核验记录。',
    '检查在线服务是否提供下载件，记录实际交付边界；服务运行本身不等于分发。',
    "核对名为 O'Reilly 的示例文件；此名称不是许可引文。",
    '核对“当前计划范围”的文件集合，并保留实际核验记录。',
])
def test_normal_verification_actions_are_retained(text):
    validate_action_semantics(text, USAGE, [])


@pytest.mark.parametrize('opener', ["'", '"', '“', '‘'])
def test_long_incomplete_english_quote_other_delimiters_rejected(opener):
    text = '核对原文：' + opener + 'Permission is hereby granted, free of charge, to any person obtaining a copy'
    with pytest.raises(ValueError, match='incomplete embedded quote'):
        validate_action_semantics(text, USAGE, [])
