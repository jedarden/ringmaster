import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../test/test-utils'
import { Button } from './Button'

describe('Button', () => {
  it('renders children content', () => {
    render(<Button>Click Me</Button>)
    expect(screen.getByText('Click Me')).toBeInTheDocument()
  })

  it('handles click events', () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick}>Click Me</Button>)

    fireEvent.click(screen.getByText('Click Me'))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('applies primary variant styling by default', () => {
    render(<Button>Primary</Button>)
    const button = screen.getByText('Primary')
    expect(button.className).toContain('bg-purple-600')
  })

  it('applies secondary variant styling', () => {
    render(<Button variant="secondary">Secondary</Button>)
    const button = screen.getByText('Secondary')
    expect(button.className).toContain('bg-gray-600')
  })

  it('applies destructive variant styling', () => {
    render(<Button variant="destructive">Delete</Button>)
    const button = screen.getByText('Delete')
    expect(button.className).toContain('bg-red-600')
  })

  it('applies ghost variant styling', () => {
    render(<Button variant="ghost">Ghost</Button>)
    const button = screen.getByText('Ghost')
    expect(button.className).toContain('hover:bg-gray-700')
  })

  it('applies outline variant styling', () => {
    render(<Button variant="outline">Outline</Button>)
    const button = screen.getByText('Outline')
    expect(button.className).toContain('border')
    expect(button.className).toContain('bg-transparent')
  })

  it('applies sm size styling', () => {
    render(<Button size="sm">Small</Button>)
    const button = screen.getByText('Small')
    expect(button.className).toContain('h-8')
    expect(button.className).toContain('px-3')
  })

  it('applies md size styling by default', () => {
    render(<Button>Medium</Button>)
    const button = screen.getByText('Medium')
    expect(button.className).toContain('h-10')
    expect(button.className).toContain('px-4')
  })

  it('applies lg size styling', () => {
    render(<Button size="lg">Large</Button>)
    const button = screen.getByText('Large')
    expect(button.className).toContain('h-12')
    expect(button.className).toContain('px-6')
  })

  it('applies icon size styling', () => {
    render(<Button size="icon">🔍</Button>)
    const button = screen.getByText('🔍')
    expect(button.className).toContain('h-10')
    expect(button.className).toContain('w-10')
  })

  it('can be disabled', () => {
    const handleClick = vi.fn()
    render(
      <Button disabled onClick={handleClick}>
        Disabled
      </Button>
    )

    const button = screen.getByText('Disabled')
    expect(button).toBeDisabled()
    expect(button.className).toContain('disabled:opacity-50')

    fireEvent.click(button)
    expect(handleClick).not.toHaveBeenCalled()
  })

  it('accepts custom className', () => {
    render(<Button className="custom-button">Custom</Button>)
    const button = screen.getByText('Custom')
    expect(button.className).toContain('custom-button')
  })

  it('renders as a button element', () => {
    render(<Button>Button</Button>)
    const button = screen.getByRole('button')
    expect(button.tagName).toBe('BUTTON')
  })

  it('passes through HTML button attributes', () => {
    render(<Button type="submit" data-testid="submit-btn">Submit</Button>)
    const button = screen.getByTestId('submit-btn')
    expect(button).toHaveAttribute('type', 'submit')
  })
})
