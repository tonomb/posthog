import { createPostHogWidgetNode } from 'scenes/notebooks/Nodes/NodeWrapper'
import { NotebookNodeType } from '~/types'
import { JSONContent, NotebookNodeAttributeProperties, NotebookNodeProps } from '../Notebook/utils'
import { CodeEditor } from 'lib/components/CodeEditors'
import { LemonMarkdown } from 'lib/lemon-ui/LemonMarkdown'

const Component = ({ attributes }: NotebookNodeProps<NotebookNodeMarkdownAttributes>): JSX.Element => {
    return <LemonMarkdown>{attributes.markdown}</LemonMarkdown>
}

export const Settings = ({
    attributes,
    updateAttributes,
}: NotebookNodeAttributeProperties<NotebookNodeMarkdownAttributes>): JSX.Element => {
    return (
        <div className="h-40">
            <CodeEditor
                className="h-full"
                language="markdown"
                value={attributes.markdown}
                onChange={(value) => updateAttributes({ markdown: value })}
                height="100%"
                options={{
                    minimap: { enabled: false },
                    wordWrap: 'on',
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    fixedOverflowWidgets: true,
                }}
            />
        </div>
    )
}

type NotebookNodeMarkdownAttributes = {
    markdown: string
}

export const NotebookNodeMarkdown = createPostHogWidgetNode<NotebookNodeMarkdownAttributes>({
    nodeType: NotebookNodeType.Markdown,
    titlePlaceholder: 'Markdown',
    Component,
    Settings,
    heightEstimate: 300,
    minHeight: '5rem',
    startExpanded: false,
    resizeable: true,
    attributes: {
        markdown: '',
    },
})

export function buildNodeMarkdown(): JSONContent {
    return {
        type: NotebookNodeType.Markdown,
        attrs: {
            __init: {
                showSettings: true,
            },
        },
    }
}
