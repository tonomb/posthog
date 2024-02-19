import { randomString } from '../support/random'
import { insight, dashboards, dashboard } from '../productAnalytics'

describe('Dashboard', () => {
    beforeEach(() => {
        cy.intercept('GET', /api\/projects\/\d+\/insights\/\?.*/).as('loadInsightList')
        cy.intercept('PATCH', /api\/projects\/\d+\/insights\/\d+\/.*/).as('patchInsight')
        cy.intercept('POST', /\/api\/projects\/\d+\/dashboards/).as('createDashboard')

        cy.clickNavMenu('dashboards')
        cy.location('pathname').should('include', '/dashboard')
    })

    it('Adding new insight to dashboard works', () => {
        const dashboardName = randomString('to add an insight to')
        const insightName = randomString('insight to add to dashboard')

        // create and visit a dashboard to get it into turbomode cache
        dashboards.createAndGoToEmptyDashboard(dashboardName)

        insight.create(insightName)

        insight.addInsightToDashboard(dashboardName, { visitAfterAdding: true })

        cy.get('[data-attr=info-toast]').should('contain', 'Insight added to dashboard')
    })

    it('Add another dashboard with different filters', () => {
        const dashboardName = randomString('Another dashboard')

        dashboards.createAndGoToEmptyDashboard(dashboardName)
        insight.create('Pageview count')
        insight.addInsightToDashboard('Another dashboard', { visitAfterAdding: true })

        dashboard.addAnyFilter()

        cy.get('[data-attr=insights-table-empty]').should('exist')

        // go to insight, check if results are there
        cy.get('.InsightCard [data-attr=insight-card-title]').find('').click()
        cy.location('pathname').should('include', '/insights')
        cy.get('[data-attr=funnel-bar-graph]', { timeout: 30000 }).should('exist')
    })
})
