'''
Tests for notion-py renderer
'''
import pytest
from functools import partial
from notion.renderer import BaseHTMLRenderer
from notion.block import TextBlock, BulletedListBlock, PageBlock, NumberedListBlock, \
							ImageBlock
from unittest.mock import Mock

def BlockMock(blockType, inputDict, children=[]):
	mock = Mock(spec=blockType)
	mock._type = blockType._type
	mock.__dict__.update(inputDict)
	mock.children = children
	return mock

for blockCls in [TextBlock, BulletedListBlock, PageBlock, NumberedListBlock, \
					ImageBlock]:
	globals()["Mock" + blockCls.__name__] = partial(BlockMock, blockCls)


def test_TextBlock():
	'''it renders a TextBlock'''
	#arrange
	block = MockTextBlock({ 'title': 'Hold up, lemme test this block...' })

	#act
	output = BaseHTMLRenderer(block).render(pretty=False)

	#assert
	assert output == '<p>Hold up, lemme test this block...</p>'

def test_BulletedListBlock():
	'''it renders a TextBlock'''
	#arrange
	block = MockPageBlock({ 'title': 'Test Page' }, [
				MockBulletedListBlock({ 'title': ':3' }),
				MockBulletedListBlock({ 'title': ':F' }),
				MockBulletedListBlock({ 'title': '>:D'})
			])

	#act
	output = BaseHTMLRenderer(block).render(pretty=False)

	#assert
	assert output == '<h1>Test Page</h1><div class="children-list"><ul><li>:3</li><li>:F</li><li>&gt;:D</li></ul></div>'

def test_NumberedListBlock():
	'''it renders a TextBlock'''
	#arrange
	block = MockPageBlock({ 'title': 'Test Page' }, [
				MockNumberedListBlock({ 'title': ':3' }),
				MockNumberedListBlock({ 'title': ':F' }),
				MockNumberedListBlock({ 'title': '>:D'})
			])

	#act
	output = BaseHTMLRenderer(block).render(pretty=False)

	#assert
	assert output == '<h1>Test Page</h1><div class="children-list"><ol><li>:3</li><li>:F</li><li>&gt;:D</li></ol></div>'

def test_ImageBlock():
	'''it renders a TextBlock'''
	#arrange
	block = MockImageBlock({
			'caption': 'Its a me! Placeholderio',
			'display_source': 'https://via.placeholder.com/20x20',
			'source': 'https://via.placeholder.com/20x20'
		})

	#act
	output = BaseHTMLRenderer(block).render(pretty=False)

	#assert
	assert output == '<img alt="Its a me! Placeholderio" src="https://via.placeholder.com/20x20">'