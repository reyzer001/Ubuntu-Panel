<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Storage;

class Setting extends Model
{
    /**
     * Setting key that stores the company logo path on the public disk.
     */
    public const KEY_COMPANY_LOGO = 'company_logo';

    /** @var array<int, string> */
    protected $fillable = ['key', 'value'];

    /**
     * Read a setting value with the database, falling back to a default.
     */
    public static function get(string $key, ?string $default = null): ?string
    {
        $value = static::query()->where('key', $key)->value('value');

        return $value ?? $default;
    }

    /**
     * Create or update a setting and refresh its cache entry.
     */
    public static function put(string $key, ?string $value): void
    {
        static::updateOrCreate(['key' => $key], ['value' => $value]);

        Cache::forget("setting.{$key}");
    }

    /**
     * Public URL of the uploaded company logo, or null when none was set.
     */
    public static function companyLogoUrl(): ?string
    {
        $path = Cache::remember('setting.'.static::KEY_COMPANY_LOGO, now()->addHour(), function (): ?string {
            $path = static::get(static::KEY_COMPANY_LOGO);

            if ($path === null || ! Storage::disk('public')->exists($path)) {
                return null;
            }

            return $path;
        });

        return $path === null ? null : asset('storage/'.$path);
    }
}
