import { describe, it, expect } from 'vitest'
import { render, screen } from '../../test/test-utils'
import { Badge } from './Badge'

describe('Badge', () => {
  it('renders children content', () => {
    render(<Badge>Test Label</Badge>)
    expect(screen.getByText('Test Label')).toBeInTheDocument()
  })

  it('applies default variant styling', () => {
    render(<Badge>Default</Badge>)
    const badge = screen.getByText('Default')
    expect(badge.className).toContain('bg-purple-600')
  })

  it('applies secondary variant styling', () => {
    render(<Badge variant="secondary">Secondary</Badge>)
    const badge = screen.getByText('Secondary')
    expect(badge.className).toContain('bg-gray-600')
  })

  it('applies success variant styling', () => {
    render(<Badge variant="success">Success</Badge>)
    const badge = screen.getByText('Success')
    expect(badge.className).toContain('bg-green-600')
  })

  it('applies warning variant styling', () => {
    render(<Badge variant="warning">Warning</Badge>)
    const badge = screen.getByText('Warning')
    expect(badge.className).toContain('bg-yellow-600')
  })

  it('applies destructive variant styling', () => {
    render(<Badge variant="destructive">Destructive</Badge>)
    const badge = screen.getByText('Destructive')
    expect(badge.className).toContain('bg-red-600')
  })

  it('applies outline variant styling', () => {
    render(<Badge variant="outline">Outline</Badge>)
    const badge = screen.getByText('Outline')
    expect(badge.className).toContain('border')
    expect(badge.className).toContain('border-gray-600')
  })

  it('applies xs size styling', () => {
    render(<Badge size="xs">XS Badge</Badge>)
    const badge = screen.getByText('XS Badge')
    expect(badge.className).toContain('text-xs')
    expect(badge.className).toContain('px-1.5')
  })

  it('applies sm size styling by default', () => {
    render(<Badge>SM Badge</Badge>)
    const badge = screen.getByText('SM Badge')
    expect(badge.className).toContain('text-xs')
    expect(badge.className).toContain('px-2')
  })

  it('applies md size styling', () => {
    render(<Badge size="md">MD Badge</Badge>)
    const badge = screen.getByText('MD Badge')
    expect(badge.className).toContain('text-sm')
    expect(badge.className).toContain('px-2.5')
  })

  it('accepts custom className', () => {
    render(<Badge className="custom-class">Custom</Badge>)
    const badge = screen.getByText('Custom')
    expect(badge.className).toContain('custom-class')
  })

  it('renders complex children', () => {
    render(
      <Badge>
        <span data-testid="inner">Inner Content</span>
      </Badge>
    )
    expect(screen.getByTestId('inner')).toBeInTheDocument()
  })
})
