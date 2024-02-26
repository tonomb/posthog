import { IconLock } from '@posthog/icons'
import { LemonButton, LemonInput, LemonSelect, LemonSkeleton, Tooltip } from '@posthog/lemon-ui'
import { useActions, useValues } from 'kea'
import { Form } from 'kea-forms'
import { NotFound } from 'lib/components/NotFound'
import { LemonField } from 'lib/lemon-ui/LemonField'
import { LemonMarkdown } from 'lib/lemon-ui/LemonMarkdown'
import React from 'react'
import { BatchExportsEditFields } from 'scenes/batch_exports/BatchExportEditForm'
import { BatchExportConfigurationForm } from 'scenes/batch_exports/batchExportEditLogic'
import { getConfigSchemaArray, isValidField } from 'scenes/pipeline/configUtils'
import { PluginField } from 'scenes/plugins/edit/PluginField'

import { PipelineStage, PluginType } from '~/types'

import { pipelineDestinationsLogic } from './destinationsLogic'
import { frontendAppsLogic } from './frontendAppsLogic'
import { importAppsLogic } from './importAppsLogic'
import { pipelineNodeLogic } from './pipelineNodeLogic'
import { pipelineTransformationsLogic } from './transformationsLogic'
import { PipelineBackend, PipelineNode } from './types'

export function PipelineNodeConfiguration(): JSX.Element {
    const {
        id,
        stage,
        newSelected,
        node,
        savedConfiguration,
        configuration,
        isConfigurationSubmitting,
        isConfigurable,
    } = useValues(pipelineNodeLogic)
    const { resetConfiguration, submitConfiguration, setNewSelected, setNewPluginNode } = useActions(pipelineNodeLogic)

    let selector = <></>

    const isNew = id === 'new'

    if (isNew) {
        if (!stage) {
            return <NotFound object="pipeline app stage" />
        }

        let plugins: Record<number, PluginType> = {}
        // TODO: do not allow creating plugin-configs for already existing plugins enabled or disabled
        if (stage === PipelineStage.Transformation) {
            plugins = useValues(pipelineTransformationsLogic).plugins
        } else if (stage === PipelineStage.Destination) {
            plugins = useValues(pipelineDestinationsLogic).plugins
        } else if (stage === PipelineStage.SiteApp) {
            plugins = useValues(frontendAppsLogic).plugins
        } else if (stage === PipelineStage.ImportApp) {
            plugins = useValues(importAppsLogic).plugins
        }

        selector = (
            <LemonSelect
                value={newSelected}
                onChange={(newValue) => {
                    setNewSelected(newValue)
                    if (newValue !== null) {
                        // TODO: why can this be null anyway
                        setNewPluginNode(plugins[newValue])
                    }
                }}
                options={Object.values(plugins).map((plugin) => ({
                    value: plugin.id,
                    label: plugin.name, // TODO: Ideally this would show RenderApp or MinimalAppView
                }))}
            />
        )
    }

    return (
        <div className="space-y-3">
            {selector}
            {!node ? (
                Array(2)
                    .fill(null)
                    .map((_, index) => (
                        <div key={index} className="space-y-2">
                            <LemonSkeleton className="h-4 w-48" />
                            <LemonSkeleton className="h-9" />
                        </div>
                    ))
            ) : (
                <>
                    <Form logic={pipelineNodeLogic} formKey="configuration" className="space-y-3">
                        {/* TODO: prefill from values or plugin name and description */}
                        <LemonField
                            name="name"
                            label="Name"
                            info="Customising the name can be useful if multiple instances of the same type are used."
                        >
                            <LemonInput type="text" />
                        </LemonField>
                        <LemonField
                            name="description"
                            label="Description"
                            info="Add a description to share context with other team members"
                        >
                            <LemonInput type="text" />
                        </LemonField>
                        {!isConfigurable ? (
                            <span>This {node.stage} isn't configurable.</span>
                        ) : node.backend === PipelineBackend.Plugin ? (
                            <PluginConfigurationFields node={node} formValues={configuration} />
                        ) : (
                            <BatchExportConfigurationFields isNew={false} formValues={configuration} />
                        )}
                        <div className="flex gap-2">
                            <LemonButton
                                type="secondary"
                                htmlType="reset"
                                onClick={() => resetConfiguration(savedConfiguration || {})}
                                disabledReason={isConfigurationSubmitting ? 'Saving in progress…' : undefined}
                            >
                                {isNew ? 'Reset' : 'Cancel'}
                            </LemonButton>
                            <LemonButton
                                type="primary"
                                htmlType="submit"
                                onClick={submitConfiguration}
                                loading={isConfigurationSubmitting}
                            >
                                {isNew ? 'Create' : 'Save'}
                            </LemonButton>
                        </div>
                    </Form>
                </>
            )}
        </div>
    )
}

function PluginConfigurationFields({
    node,
}: {
    node: PipelineNode & { backend: PipelineBackend.Plugin }
    formValues: Record<string, any>
}): JSX.Element {
    const { hiddenFields, requiredFields } = useValues(pipelineNodeLogic)

    const configSchemaArray = getConfigSchemaArray(node.plugin.config_schema)
    const fields = configSchemaArray.map((fieldConfig, index) => (
        <React.Fragment key={fieldConfig.key || `__key__${index}`}>
            {fieldConfig.key &&
            fieldConfig.type &&
            isValidField(fieldConfig) &&
            !hiddenFields.includes(fieldConfig.key) ? (
                <LemonField
                    name={fieldConfig.key}
                    label={
                        <>
                            {fieldConfig.secret && (
                                <Tooltip
                                    placement="top-start"
                                    title="This field is write-only. Its value won't be visible after saving."
                                >
                                    <IconLock className="ml-1.5" />
                                </Tooltip>
                            )}
                            {fieldConfig.markdown && <LemonMarkdown>{fieldConfig.markdown}</LemonMarkdown>}
                            {fieldConfig.name || fieldConfig.key}
                        </>
                    }
                    help={fieldConfig.hint && <LemonMarkdown className="mt-0.5">{fieldConfig.hint}</LemonMarkdown>}
                    showOptional={!requiredFields.includes(fieldConfig.key)}
                >
                    <PluginField fieldConfig={fieldConfig} />
                </LemonField>
            ) : (
                <>
                    {fieldConfig.type ? (
                        <p className="text-danger">
                            Invalid config field <i>{fieldConfig.name || fieldConfig.key}</i>.
                        </p>
                    ) : null}
                </>
            )}
        </React.Fragment>
    ))

    return <>{fields}</>
}

function BatchExportConfigurationFields({
    isNew,
    formValues,
}: {
    isNew: boolean
    formValues: Record<string, any>
}): JSX.Element {
    return (
        <BatchExportsEditFields
            isNew={isNew}
            isPipeline
            batchExportConfigForm={formValues as BatchExportConfigurationForm}
        />
    )
}
