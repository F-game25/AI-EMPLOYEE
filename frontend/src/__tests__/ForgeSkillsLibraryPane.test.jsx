import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SkillsLibraryPane } from '../components/pages/forge/panels.jsx'

vi.mock('../api/client', () => ({
  default: {
    forge: {
      getSkills: vi.fn().mockResolvedValue({
        ok: true,
        skills: [{
          id: 'skill_registry_validator',
          name: 'Skill Registry Validator',
          description: 'Validates the skill registry.',
          maturity_level: 'production_batch_1',
          safety_level: 'low',
          execution_mode: 'tool_guided_llm',
          requires_human_approval: false,
          tools_allowed: ['read_file'],
          success_criteria: ['Registry is valid'],
          test_cases: [{ name: 'selects_skill_registry_validator' }],
          ui_metadata: { wired: true, batch: 'batch_1' },
        }],
      }),
      reloadSkills: vi.fn(),
    },
  },
}))

describe('Forge SkillsLibraryPane', () => {
  it('renders production metadata for canonical skill ids', async () => {
    render(<SkillsLibraryPane project={{ id: 'p1' }} />)

    await waitFor(() => expect(screen.getByText('Skill Registry Validator')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Skill Registry Validator'))

    expect(screen.getByText('skill_registry_validator')).toBeInTheDocument()
    expect(screen.getByText('WIRED')).toBeInTheDocument()
    expect(screen.getByText('production_batch_1')).toBeInTheDocument()
    expect(screen.getByText('safety: low')).toBeInTheDocument()
    expect(screen.getByText('tool_guided_llm')).toBeInTheDocument()
    expect(screen.getByText('1 tests')).toBeInTheDocument()
    expect(screen.getByText('read_file')).toBeInTheDocument()
    expect(screen.getByText('- Registry is valid')).toBeInTheDocument()
  })
})
