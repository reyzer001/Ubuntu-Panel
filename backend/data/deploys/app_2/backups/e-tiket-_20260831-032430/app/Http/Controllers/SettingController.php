<?php

namespace App\Http\Controllers;

use App\Models\Setting;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use Illuminate\View\View;

class SettingController extends Controller
{
    /**
     * Show the company profile settings form.
     */
    public function edit(): View
    {
        return view('admin.settings', [
            'companyLogoUrl' => Setting::companyLogoUrl(),
        ]);
    }

    /**
     * Replace the company logo. The previous logo stays in use until
     * a new one is uploaded.
     */
    public function update(Request $request): RedirectResponse
    {
        $request->validate([
            'logo' => ['required', 'image', 'mimes:jpg,jpeg,png', 'max:2048'],
        ]);

        $path = $request->file('logo')->store('logo', 'public');

        $previous = Setting::get(Setting::KEY_COMPANY_LOGO);

        if ($previous !== null && Storage::disk('public')->exists($previous)) {
            Storage::disk('public')->delete($previous);
        }

        Setting::put(Setting::KEY_COMPANY_LOGO, $path);

        return redirect()->route('admin.settings.edit')->with('success', 'Logo perusahaan berhasil diperbarui.');
    }
}
