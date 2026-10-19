<?php

namespace App\Http\Controllers;

use App\Models\Category;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;

class AdminCategoryController extends Controller
{
    /**
     * Display a listing of categories.
     */
    public function index(): View
    {
        $categories = Category::orderBy('name', 'asc')->get();

        return view('admin.categories', compact('categories'));
    }

    /**
     * Store a newly created category.
     */
    public function store(Request $request): RedirectResponse
    {
        $request->validate([
            'name' => ['required', 'string', 'max:255', 'unique:categories'],
            'sla_response_minutes' => ['required', 'integer', 'min:1'],
            'sla_resolve_minutes' => ['required', 'integer', 'min:1'],
        ]);

        Category::create([
            'name' => $request->name,
            'sla_response_minutes' => $request->sla_response_minutes,
            'sla_resolve_minutes' => $request->sla_resolve_minutes,
        ]);

        return redirect()->route('admin.categories.index')->with('success', 'Kategori baru berhasil ditambahkan.');
    }

    /**
     * Update the specified category.
     */
    public function update(Request $request, Category $category): RedirectResponse
    {
        $request->validate([
            'name' => ['required', 'string', 'max:255', 'unique:categories,name,'.$category->id],
            'sla_response_minutes' => ['required', 'integer', 'min:1'],
            'sla_resolve_minutes' => ['required', 'integer', 'min:1'],
        ]);

        $category->update([
            'name' => $request->name,
            'sla_response_minutes' => $request->sla_response_minutes,
            'sla_resolve_minutes' => $request->sla_resolve_minutes,
        ]);

        return redirect()->route('admin.categories.index')->with('success', 'Kategori berhasil diperbarui.');
    }

    /**
     * Remove the specified category from storage.
     */
    public function destroy(Category $category): RedirectResponse
    {
        // Check if there are active tickets using this category
        $ticketCount = $category->tickets()->count();

        if ($ticketCount > 0) {
            return back()->with('error', "Kategori tidak dapat dihapus karena sedang digunakan oleh {$ticketCount} tiket.");
        }

        $category->delete();

        return redirect()->route('admin.categories.index')->with('success', 'Kategori berhasil dihapus.');
    }
}
