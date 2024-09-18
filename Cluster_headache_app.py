#!/usr/bin/env python
# coding: utf-8

# # Cluster headache simulations: Streamlined full model

import numpy as np
from scipy.stats import lognorm, gmean, rv_discrete, beta, truncnorm, expon
from scipy.optimize import minimize, curve_fit, OptimizeWarning
import warnings
from dataclasses import dataclass
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from matplotlib.ticker import FuncFormatter
import streamlit as st

# ## Annual bout frequency for episodic patients

data = {
    # Discretized approximation for a distribution with mean 1.2, SD 1.1
    'Gaul': {'n': 209, 'dist': {1: 0.6, 2: 0.3, 3: 0.1}},  
    
    # Split "<1/year" between 0 and 1, ">1/year" between 2 and 3
    'Li': {'n': 327, 'dist': {0.5: 0.416, 1: 0.370, 2.5: 0.214}},
    
    # Split "1/1.5-2 years" between 0 and 1
    'Friedman': {'n': 50, 'dist': {0.5: 0.46, 1: 0.54}},
    
    # Split "<1/year" between 0 and 1
    'Ekbom': {'n': 105, 'dist': {0.5: 0.14, 1: 0.40, 2: 0.31, 3: 0.15}},
    
    # Split "1-2/year" evenly between 1 and 2
    'Manzoni': {'n': 161, 'dist': {1: 0.27, 1.5: 0.73}},
    
    # Converted from remission periods to bouts/year, chronic cases removed
    'Sutherland': {'n': 49, 'dist': {
        0.5: 0.512+0.174,  # 1-5 years, adding >5 years for simplicity
        1: 0.140,    # 6-12 months
        2: 0.174     # 3-6 months
    }},
    
    # Estimated from remission periods, splitting some categories
    'Kudrow': {'n': 428, 'dist': {0.5: 0.19, 1: 0.67, 2.5: 0.14}}
}

# Combine distributions
combined_dist = {}
total_n = sum(study['n'] for study in data.values())

for study in data.values():
    weight = study['n'] / total_n
    for bouts, prob in study['dist'].items():
        combined_dist[bouts] = combined_dist.get(bouts, 0) + prob * weight

# Normalize the combined distribution
total_prob = sum(combined_dist.values())
combined_dist = {k: v/total_prob for k, v in combined_dist.items()}

# Create custom discrete distribution
bouts_per_year = rv_discrete(values=(list(combined_dist.keys()), list(combined_dist.values())))


# ## Bout duration for episodic patients

data = []
sample_sizes = []

# Gaul et al. (2012)
data.append(8.5)
sample_sizes.append(209)

# Li et al. (2022)
total_li = 327
original_proportions = np.array([0.104, 0.235, 0.502, 0.131])
sum_proportions = np.sum(original_proportions)
new_proportions = original_proportions / sum_proportions
data.extend([1, gmean([2, 4]), gmean([4, 8]), 8])
sample_sizes.extend([int(prop * total_li) for prop in new_proportions])

# Friedman & Mikropoulos (1958)
data.append(gmean([6, 8]))
sample_sizes.append(50)

# Ekbom (1970)
data.append(gmean([4, 12]))
sample_sizes.append(105)

# Lance & Anthony (1971)
data.append(gmean([2, 12]))
sample_sizes.append(60)

# Sutherland & Eadie (1972)
total_sutherland = 58
data.extend([np.mean([0, 4]), gmean([5, 13]), gmean([14, 26]), gmean([27, 52])])
sample_sizes.extend([int(0.23 * total_sutherland), int(0.45 * total_sutherland), 
                     int(0.19 * total_sutherland), int(0.14 * total_sutherland)])

# Rozen & Fishman (2012)
data.append(10.3)
sample_sizes.append(101)

# Manzoni et al. (1983)
data.append(gmean([4, 8]))
sample_sizes.append(161)

# Convert to numpy arrays
data = np.array(data)
sample_sizes = np.array(sample_sizes)

# Use sample sizes as weights
weights = sample_sizes / np.sum(sample_sizes)

# Fitting the lognormal distribution
def neg_log_likelihood(params):
    mu, sigma = params
    return -np.sum(weights * lognorm.logpdf(data, s=sigma, scale=np.exp(mu)))

initial_params = [np.log(np.average(data, weights=weights)), 0.5]
result = minimize(neg_log_likelihood, initial_params, method='Nelder-Mead')
optimal_mu, optimal_sigma = result.x


# ## Modeling attacks per day for both episodic and chronic CH sufferers

def fit_lognormal(mean, std):
    """
    Fit a lognormal distribution given mean and standard deviation.
    Returns the mu and sigma parameters of the lognormal distribution.
    """
    variance = std**2
    mu = np.log(mean**2 / np.sqrt(variance + mean**2))
    sigma = np.sqrt(np.log(1 + variance / mean**2))
    return mu, sigma

def truncated_lognorm_pdf(x, mu, sigma, upper_bound=np.inf):
    """
    Calculate the PDF of a truncated lognormal distribution.
    """
    pdf = lognorm.pdf(x, s=sigma, scale=np.exp(mu))
    cdf_upper = lognorm.cdf(upper_bound, s=sigma, scale=np.exp(mu))
    return np.where(x <= upper_bound, pdf / cdf_upper, 0)

def estimate_untreated(treated_mean, treated_std, treatment_effect=1.05):
    """
    Function to estimate untreated values
    """
    cv = treated_std / treated_mean  # Coefficient of variation
    untreated_mean = treated_mean * treatment_effect
    untreated_std = untreated_mean * cv
    return untreated_mean, untreated_std

def generate_attacks_per_day(is_chronic, is_treated, max_daily_ch=np.inf):
    if is_chronic:
        if is_treated:
            mu, sigma = chronic_treated_mu, chronic_treated_sigma
        else:
            mu, sigma = chronic_untreated_mu, chronic_untreated_sigma
    else:
        if is_treated:
            mu, sigma = episodic_treated_mu, episodic_treated_sigma
        else:
            mu, sigma = episodic_untreated_mu, episodic_untreated_sigma
    
    while True:
        attacks = lognorm.rvs(s=sigma, scale=np.exp(mu))
        if attacks <= max_daily_ch:
            break
    
    return max(1, round(attacks))

# Gaul et al. (2012) data for treated patients (not explicitly stated in the paper,
# but highly likely given that they were German patients from a hospital)
episodic_treated_mean, episodic_treated_std = 3.1, 2.1
chronic_treated_mean, chronic_treated_std = 3.3, 3.0

# Estimating untreated values
episodic_untreated_mean, episodic_untreated_std = estimate_untreated(episodic_treated_mean, episodic_treated_std)
chronic_untreated_mean, chronic_untreated_std = estimate_untreated(chronic_treated_mean, chronic_treated_std)

# Fit lognormal distributions
episodic_treated_mu, episodic_treated_sigma = fit_lognormal(episodic_treated_mean, episodic_treated_std)
chronic_treated_mu, chronic_treated_sigma = fit_lognormal(chronic_treated_mean, chronic_treated_std)
episodic_untreated_mu, episodic_untreated_sigma = fit_lognormal(episodic_untreated_mean, episodic_untreated_std)
chronic_untreated_mu, chronic_untreated_sigma = fit_lognormal(chronic_untreated_mean, chronic_untreated_std)


# ## Simulating active days for chronic patients

def generate_chronic_active_days():
    while True:
        # Generate total attack days in a year
        active_days = int(lognorm.rvs(s=.5, scale=np.exp(np.log(200))))
        
        # Ensure active_days is never over 365
        active_days = min(active_days, 365)
        
        return active_days


# ## Simulating attack durations

def generate_attack_duration(is_chronic, is_treated, max_intensities, size):
    # Base parameters for lognormal distribution
    mu = 4.0
    sigma = 0.4
    
    if is_chronic:
        mu += 0.3  # Slightly longer attacks for chronic sufferers
    
    # Generate base durations
    base_durations = lognorm.rvs(s=sigma, scale=np.exp(mu), size=size)
    
    # Adjust durations based on max intensities
    # This creates a positive correlation between intensity and duration
    intensity_factor = 0.1064 * max_intensities + 0.5797 # Scale factor based on intensity
    adjusted_durations = base_durations * intensity_factor

    if is_treated:
        # Reasoning: Patients with access to treatment will, in some cases, manage to reduce
        # the duration of the attack. However, according to Snoer et al., mild attacks are often
        # not treated despite having access to treatment, and those are typically shorter, which explains
        # the seemingly contradictory statistic about untreated attacks being shorter.
        
        max_effect = 0.3  # Up to 30% duration reduction for highest intensity
        
        intensity_normalized = (max_intensities - 1) / 9
        
        # The more intense the attack, the more a patient will use treatment to abort the attack (shorter duration)
        mean_effect = 1 - (max_effect * intensity_normalized)
        
        # However, treatment might or might not be effective, so model this using a beta distribution.
        a, b = 5, 2
        treatment_effect = beta.rvs(a, b, size=size) * mean_effect
        
        # Apply treatment effect
        adjusted_durations *= treatment_effect
    
    return np.clip(np.round(adjusted_durations).astype(int), 15, 360)


# ## Simulating max pain intensity

def generate_max_pain_intensity(is_treated, size):
    
    mean_mild_moderate = 4.0
    sd_mild_moderate = 2.0
    mean_moderate_severe = 7.5
    sd_moderate_severe = 2.0
    scale_very_severe = .7 if is_treated else 0.5
    
    mild_to_moderate = truncnorm.rvs((1-mean_mild_moderate)/sd_mild_moderate, np.inf, loc=mean_mild_moderate, scale=sd_mild_moderate, size=size)
    moderate_to_severe = truncnorm.rvs((1-mean_moderate_severe)/sd_moderate_severe, np.inf, loc=mean_moderate_severe, scale=sd_moderate_severe, size=size)
    very_severe = 10 - expon.rvs(scale=scale_very_severe, size=size)
    
    if is_treated:
        # For treated patients:
        choices = np.random.choice(3, size=size, p=[0.40, 0.35, 0.25])
    else:
        # For untreated patients:
        choices = np.random.choice(3, size=size, p=[0.20, 0.50, 0.30])

    intensities = np.where(choices == 0, mild_to_moderate,
                  np.where(choices == 1, moderate_to_severe, very_severe))
    
    return np.round(np.clip(intensities, 1, 10), decimals=1)


# ## Defining classes for attacks and patients

@dataclass
class Attack:
    total_duration: int
    max_intensity: float
    max_intensity_duration: int

class Patient:
    def __init__(self, is_chronic, is_treated):
        self.is_chronic = is_chronic
        self.is_treated = is_treated
        self.attacks = []
        self.generate_profile()
        self.pre_generate_attack_pool()

    def generate_profile(self):
        if self.is_chronic:
            self.active_days = generate_chronic_active_days()
        else:
            self.annual_bouts = bouts_per_year.rvs()
            self.bout_durations = self.generate_bout_durations()

    def pre_generate_attack_pool(self):
        # Estimate the maximum number of attacks in a year
        if self.is_chronic:
            max_attacks = self.active_days * 8  # Assuming max 8 attacks per day
        else:
            max_attacks = sum(self.bout_durations) * 8

        # Generate a pool of attacks
        max_intensities = generate_max_pain_intensity(is_treated=self.is_treated, size=max_attacks)
        total_durations = generate_attack_duration(self.is_chronic, self.is_treated, max_intensities, size=max_attacks)
        # Assuming onset and offset phases take up 15% of the total attack duration each
        max_intensity_durations = np.round(0.7 * total_durations).astype(int)

        self.attack_pool = [Attack(total_durations[i], max_intensities[i], max_intensity_durations[i])
                            for i in range(max_attacks)]
        self.pool_index = 0
        
    def generate_bout_durations(self):
        # Use the lognormal distribution for bout durations
        n_bouts = np.ceil(self.annual_bouts)
        durations = lognorm.rvs(s=optimal_sigma, scale=np.exp(optimal_mu), size=int(n_bouts))
        
        # Adjust the last bout duration if annual_bouts is not an integer
        if self.annual_bouts != int(self.annual_bouts):
            durations[-1] *= (self.annual_bouts - int(self.annual_bouts))
        
        return [max(1, int(duration * 7)) for duration in durations]  # Convert weeks to days, ensure at least 1 day

    def generate_year_of_attacks(self):
        self.attacks = []
        total_attacks = 0
        if self.is_chronic:
            for day in range(min(365, self.active_days)):
                total_attacks += self.generate_day_attacks()
        else:
            for duration in self.bout_durations:
                for day in range(duration):
                    total_attacks += self.generate_day_attacks()
        return total_attacks

    def generate_day_attacks(self):
        daily_attacks = 0
        attacks_today = generate_attacks_per_day(self.is_chronic, self.is_treated)

        for _ in range(attacks_today):
            if self.pool_index >= len(self.attack_pool):
                # If we've used all pre-generated attacks, generate more
                self.pre_generate_attack_pool()
            
            self.attacks.append(self.attack_pool[self.pool_index])
            self.pool_index += 1
            daily_attacks += 1

        return daily_attacks

    def calculate_intensity_minutes(self):
        intensity_minutes = {}
        for attack in self.attacks:
            intensity = round(attack.max_intensity, 1)  # Round to nearest 0.1
            intensity_minutes[intensity] = intensity_minutes.get(intensity, 0) + attack.max_intensity_duration
        return intensity_minutes


# ## Functions to run the simulations

def generate_population(n_episodic_treated, n_episodic_untreated, n_chronic_treated, n_chronic_untreated):
    population = []
    for _ in range(n_episodic_treated):
        population.append(Patient(is_chronic=False, is_treated=True))
    for _ in range(n_episodic_untreated):
        population.append(Patient(is_chronic=False, is_treated=False))
    for _ in range(n_chronic_treated):
        population.append(Patient(is_chronic=True, is_treated=True))
    for _ in range(n_chronic_untreated):
        population.append(Patient(is_chronic=True, is_treated=False))
    return population


def calculate_group_data(population, groups_simulated):
    intensities = np.arange(0, 10.1, 0.1)
    group_data = []
    chronic_attacks = []
    episodic_attacks = []
    
    all_treated_attacks = []
    all_untreated_attacks = []
    all_episodic_attacks = []
    all_chronic_attacks = []
    all_treated_intensities = []
    all_untreated_intensities = []
    all_episodic_intensities = []
    all_chronic_intensities = []

    for group_name, condition, n_patients in groups_simulated:
        group_patients = [p for p in population if condition(p)]
        total_intensity_minutes = {}
        intensity_minutes_list = {round(i, 1): [] for i in intensities}
        group_total_attacks = []
        group_intensities = []
        
        for patient in group_patients:
            total_attacks = patient.generate_year_of_attacks()
            group_total_attacks.append(total_attacks)
            
            patient_intensity_minutes = patient.calculate_intensity_minutes()
            for intensity, minutes in patient_intensity_minutes.items():
                rounded_intensity = round(intensity, 1)
                total_intensity_minutes[rounded_intensity] = total_intensity_minutes.get(rounded_intensity, 0) + minutes
                intensity_minutes_list[rounded_intensity].append(minutes)
                group_intensities.extend([intensity] * int(minutes))
        
        intensity_minutes_average = [total_intensity_minutes.get(round(i, 1), 0) / n_patients for i in intensities]
        intensity_minutes_std = [np.std(intensity_minutes_list[round(i, 1)]) if intensity_minutes_list[round(i, 1)] else 0 for i in intensities]
        intensity_minutes_total = [total_intensity_minutes.get(round(i, 1), 0) for i in intensities]
        group_data.append((group_name, intensity_minutes_average, intensity_minutes_std, intensity_minutes_total, n_patients))
        
        # Calculate statistics (without printing)
        attack_stats = np.percentile(group_total_attacks, [25, 50, 75])
        intensity_stats = np.percentile(group_intensities, [25, 50, 75])
        
        if 'Chronic' in group_name:
            chronic_attacks.extend(group_total_attacks)
            all_chronic_attacks.extend(group_total_attacks)
            all_chronic_intensities.extend(group_intensities)
        else:
            episodic_attacks.extend(group_total_attacks)
            all_episodic_attacks.extend(group_total_attacks)
            all_episodic_intensities.extend(group_intensities)
        
        if 'Treated' in group_name:
            all_treated_attacks.extend(group_total_attacks)
            all_treated_intensities.extend(group_intensities)
        else:
            all_untreated_attacks.extend(group_total_attacks)
            all_untreated_intensities.extend(group_intensities)
    
    return intensities, group_data

def transform_intensity(intensities, method='linear', power=2, max_value=100):
    """
    Transform the intensity scale based on the specified method.
    
    :param intensities: Array of original intensity values (0-10 scale)
    :param method: The transformation method ('linear', 'power', 'power_scaled', 'custom_exp', 'piecewise_linear', or 'log')
    :param power: The power to use for the power law transformation
    :param max_value: The maximum value of the transformed scale (required for all methods)
    :return: Array of transformed intensity values
    """
    if max_value <= 0:
        raise ValueError("max_value must be positive")

    if method == 'linear':
        return intensities * (max_value / 10)
    
    elif method == 'power':
        return (intensities ** power) * (max_value / (10 ** power))

    elif method == 'power_scaled':
        return (intensities / 10)**power * max_value
    
    elif method == 'custom_exp':
        exp_func = lambda x, A, B, C: A * np.exp(B * x) + C
        x = np.array([0, 7.42, 10])
        y = np.array([0, max_value/2, max_value])
        
        # Adjust initial parameters based on max_value
        p0 = np.array([max_value/10, 0.5, 0])
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            warnings.simplefilter("ignore", category=OptimizeWarning)
            try:
                A, B, C = curve_fit(exp_func, x, y, p0=p0, maxfev=10000)[0]
            except RuntimeError:
                print(f"Curve fitting failed for max_value={max_value}. Using fallback linear transformation.")
                return intensities * (max_value / 10)
        
        return exp_func(intensities, A, B, C)
    
    elif method == 'piecewise_linear':
        breakpoint = 8
        lower_slope = (max_value / 2) / breakpoint
        upper_slope = (max_value / 2) / (10 - breakpoint)
        return np.where(intensities <= breakpoint,
                        lower_slope * intensities,
                        (max_value / 2) + upper_slope * (intensities - breakpoint))
    
    elif method == 'log':
        # I(x) = 10^(x/25) - 1, scaled to max_value
        return (10**(intensities/2.5) - 1) * (max_value / (10**(10/2.5) - 1))
    
    else:
        raise ValueError("Invalid method. Choose 'linear', 'power', 'power_scaled', 'custom_exp', 'piecewise_linear', or 'log'.")

def calculate_adjusted_pain_units(time_amounts, transformation_method, power, max_value):
    intensities = np.arange(0, 10.1, 0.1)
    transformed_intensities = transform_intensity(intensities, method=transformation_method, power=power, max_value=max_value)
    adjusted_pain_units = [y * t for y, t in zip(time_amounts, transformed_intensities)]
    
    return adjusted_pain_units
    
def create_plot(fig, data, intensities, colors, markers, title, y_title):
    for i, (name, values, std) in enumerate(data):
        color = colors[i % len(colors)]
        rgb_color = tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        marker = markers[i % len(markers)]
        
        # Lower bound of shaded area
        fig.add_trace(go.Scatter(
            x=intensities,
            y=[max(0, v - s) for v, s in zip(values, std)],
            mode='lines',
            line=dict(width=0),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Upper bound of shaded area
        fig.add_trace(go.Scatter(
            x=intensities,
            y=[v + s for v, s in zip(values, std)],
            mode='lines',
            line=dict(width=0),
            fill='tonexty',
            fillcolor=f'rgba({rgb_color[0]},{rgb_color[1]},{rgb_color[2]},0.2)',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Main line with markers
        fig.add_trace(go.Scatter(
            x=intensities,
            y=values,
            mode='lines+markers',
            name=name,
            line=dict(color=color, width=2),
            marker=dict(
                symbol=marker,
                size=[8 if x.is_integer() else 0 for x in intensities],
                color=color,
            ),
            hoverinfo='x+y+name'
        ))

    y_format = ',.0f'

    fig.update_layout(
        title=title,
        xaxis_title='Pain Intensity',
        yaxis_title=y_title,
        xaxis=dict(tickmode='linear', tick0=0, dtick=1),
        yaxis=dict(tickformat=y_format),
        legend_title_text='',
        hovermode='closest',
        template='plotly_dark',
        legend=dict(
            itemsizing='constant',
            itemwidth=30,
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(0,0,0,0.5)",  # Semi-transparent background
            bordercolor="white",
            borderwidth=1
        )
    )

    return fig

# Function to create bar plot
def create_bar_plot(groups, values, errors, title, y_title):
    
    # Create color map
    color_map = {
        'Episodic Treated': px.colors.qualitative.Plotly[0],
        'Episodic Untreated': px.colors.qualitative.Plotly[1],
        'Chronic Treated': px.colors.qualitative.Plotly[2],
        'Chronic Untreated': px.colors.qualitative.Plotly[3]
    }
    
    fig = go.Figure(data=[
        go.Bar(
            x=groups,
            y=values,
            error_y=dict(type='data', array=errors, visible=True),
            marker=dict(
                color=[color_map[group] for group in groups],
                opacity=0.7,
                line=dict(width=1, color='white')
            )
        )
    ])
    
    fig.update_layout(
        title=title,
        yaxis_title=y_title,
        template='plotly_dark',
        yaxis=dict(tickformat=',.0f'),
        showlegend=False,
        bargap=0.3
    )
    return fig

def create_comparison_plot(bar_values, bar_errors):
    bar_labels = ['Total Person-Years', 'Person-Years at ≥9/10 Intensity']

    fig_comparison = go.Figure(data=[
        go.Bar(
            x=bar_labels,
            y=bar_values,
            error_y=dict(type='data', array=bar_errors, visible=True),
            marker=dict(
                color=['blue', 'red'],
                opacity=0.7,
                line=dict(width=1, color='white')
            )
        )
    ])

    fig_comparison.update_layout(
        title='Comparison of Total and ≥9/10 Intensity Person-Years Across All Groups',
        yaxis_title='Person-Years',
        template='plotly_dark',
        yaxis=dict(tickformat=',.0f'),
        showlegend=False,
        bargap=0.3
    )

    return fig_comparison

def format_with_adjusted(value, adjusted):
    return f"{value:,.0f} ({adjusted:,.0f})"

def create_summary_table(ch_groups, avg_data, total_person_years, high_intensity_person_years, adjusted_pain_units, transformation_method, power, max_value):
    table_data = []
    total_row = {
        'Group': 'Total',
        'Average Patient': {key: 0 for key in ['Minutes', 'High-Intensity Minutes', 'Adjusted Units', 'High-Intensity Adjusted Units']},
        'Global Estimate': {key: 0 for key in ['Person-Years', 'High-Intensity Person-Years', 'Adjusted Units', 'High-Intensity Adjusted Units']}
    }

def create_summary_table(ch_groups, avg_data, total_person_years, high_intensity_person_years, adjusted_pain_units, adjusted_avg_pain_units):
    table_data = []
    total_row = {
        'Group': 'Total',
        'Average Patient': {key: 0 for key in ['Minutes', 'High-Intensity Minutes', 'Adjusted Units', 'High-Intensity Adjusted Units']},
        'Global Estimate': {key: 0 for key in ['Person-Years', 'High-Intensity Person-Years', 'Adjusted Units', 'High-Intensity Adjusted Units']}
    }

    avg_data_dict = {name: avg for name, avg, _ in avg_data}

    for group in ch_groups.keys():
        avg_minutes = sum(avg_data_dict[group])
        avg_high_minutes = sum(avg_data_dict[group][90:])
        global_years = total_person_years[group]
        global_high_years = high_intensity_person_years[group]
        
        avg_adjusted_units = sum(adjusted_avg_pain_units[group])
        avg_high_adjusted_units = sum(adjusted_avg_pain_units[group][90:])
        
        global_adjusted_units = sum(adjusted_pain_units[group])
        global_high_adjusted_units = sum(adjusted_pain_units[group][90:])
        
        row = {
            'Group': group,
            'Average Patient': {
                'Minutes': avg_minutes,
                'High-Intensity Minutes': avg_high_minutes,
                'Adjusted Units': avg_adjusted_units,
                'High-Intensity Adjusted Units': avg_high_adjusted_units
            },
            'Global Estimate': {
                'Person-Years': global_years,
                'High-Intensity Person-Years': global_high_years,
                'Adjusted Units': global_adjusted_units,
                'High-Intensity Adjusted Units': global_high_adjusted_units
            }
        }
        table_data.append(row)
        
        # Update total row
        for category in ['Average Patient', 'Global Estimate']:
            for key in total_row[category].keys():
                total_row[category][key] += row[category][key]
    
    table_data.append(total_row)
    return table_data

def create_dataframe(table_data):
    df_data = [
        {
            'Group': row['Group'],
            'Minutes': format_with_adjusted(row['Average Patient']['Minutes'], row['Average Patient']['Adjusted Units']),
            'High-Intensity Minutes': format_with_adjusted(row['Average Patient']['High-Intensity Minutes'], row['Average Patient']['High-Intensity Adjusted Units']),
            'Person-Years': format_with_adjusted(row['Global Estimate']['Person-Years'], row['Global Estimate']['Adjusted Units']),
            'High-Intensity Person-Years': format_with_adjusted(row['Global Estimate']['High-Intensity Person-Years'], row['Global Estimate']['High-Intensity Adjusted Units'])
        }
        for row in table_data
    ]
    df = pd.DataFrame(df_data)
    
    df.columns = pd.MultiIndex.from_tuples([
        ('', 'Group'),
        ('Average Patient', 'Total Minutes in Pain'),
        ('Average Patient', 'Minutes in ≥9/10 Pain'),
        ('Global Estimate', 'Total Person-Years in Pain'),
        ('Global Estimate', 'Person-Years in ≥9/10 Pain')
    ])
    
    return df

def display_summary_table(df):
    css = """
    <style>
        .dataframe {
            width: 100%;
            text-align: right;
            border-collapse: collapse;
            font-size: 0.9em;
            color: #333;
            background-color: #f8f8f8;
            border-left: none;
            border-right: none;
        }
        .dataframe th, .dataframe td {
            border-top: 1px solid #ddd;
            border-bottom: 1px solid #ddd;
            border-left: none;
            border-right: none;
            padding: 8px;
            white-space: pre-wrap;
            word-wrap: break-word;
            max-width: 150px;
            text-align: center;  /* Center-align all cells */
        }
        .dataframe thead tr:nth-child(1) th {
            background-color: #e0e0e0;
            text-align: center;
            font-weight: bold;
            color: #333;
        }
        .dataframe thead tr:nth-child(2) th {
            background-color: #e8e8e8;
            text-align: center;
            color: #333;
        }
        .dataframe tbody tr:nth-child(even) {
            background-color: #f0f0f0;
        }
        .dataframe tbody tr:nth-child(odd) {
            background-color: #f8f8f8;
        }
        .dataframe tbody tr:hover {
            background-color: #e8e8e8;
        }
        .dataframe td:first-child, .dataframe th:first-child {
            text-align: left;
        }
        .table-note {
            margin-top: 10px;
            font-style: italic;
            font-size: 0.9em;
        }
        .dataframe tr:last-child {
            font-weight: bold;
        }
        @media (prefers-color-scheme: dark) {
            .dataframe, .table-note {
                color: #e0e0e0;
                background-color: #2c2c2c;
            }
            .dataframe th, .dataframe td {
                border-color: #4a4a4a;
            }
            .dataframe thead tr:nth-child(1) th,
            .dataframe thead tr:nth-child(2) th {
                background-color: #3c3c3c;
                color: #e0e0e0;
            }
            .dataframe tbody tr:nth-child(even) {
                background-color: #323232;
            }
            .dataframe tbody tr:nth-child(odd) {
                background-color: #2c2c2c;
            }
            .dataframe tbody tr:hover {
                background-color: #3a3a3a;
            }
        }
    </style>
    """
    
    table_html = df.to_html(index=False, escape=False, classes='dataframe')
    
    st.markdown(css, unsafe_allow_html=True)
    st.write(table_html, unsafe_allow_html=True)
    
# ## Streamlit app
def main():
    st.title("Global Burden of Cluster Headache Pain")

    # Sidebar for user inputs
    st.sidebar.header("Parameters")

    # Add input for annual prevalence
    annual_prevalence_per_100k = st.sidebar.number_input("Annual prevalence of CH sufferers (per 100,000)", 
                                                         min_value=1, max_value=1000, value=53, step=1)
    annual_prevalence = annual_prevalence_per_100k / 100000

    # Constants and calculations
    world_population = 8_200_000_000
    adult_fraction = 0.72
    total_ch_sufferers = world_population * adult_fraction * annual_prevalence

    st.sidebar.write(f"Total annual CH sufferers worldwide: {int(total_ch_sufferers):,}")
    
    # Add sliders for key parameters
    prop_chronic = st.sidebar.slider("Percentage of chronic patients", 0, 100, 20, format="%d%%") / 100
    prop_treated = st.sidebar.slider("Percentage of treated patients", 0, 100, 48, format="%d%%") / 100

    prop_episodic = 1 - prop_chronic
    prop_untreated = 1 - prop_treated
    
    # Add slider for fraction of patients to simulate
    percent_of_patients_to_simulate = st.sidebar.slider("Percentage of worldwide patients to simulate", 
                                                        0.01, 0.1, 0.02, 
                                                        format="%.2f%%")
    fraction_of_patients_to_simulate = percent_of_patients_to_simulate / 100

    ch_groups = {
        'Episodic Treated': int(total_ch_sufferers * prop_episodic * prop_treated),
        'Episodic Untreated': int(total_ch_sufferers * prop_episodic * prop_untreated),
        'Chronic Treated': int(total_ch_sufferers * prop_chronic * prop_treated),
        'Chronic Untreated': int(total_ch_sufferers * prop_chronic * prop_untreated)
    }

    n_episodic_treated = int(ch_groups['Episodic Treated'] * fraction_of_patients_to_simulate)
    n_episodic_untreated = int(ch_groups['Episodic Untreated'] * fraction_of_patients_to_simulate)
    n_chronic_treated = int(ch_groups['Chronic Treated'] * fraction_of_patients_to_simulate)
    n_chronic_untreated = int(ch_groups['Chronic Untreated'] * fraction_of_patients_to_simulate)

    # Display calculated total CH sufferers and simulated patients
    total_simulated = sum([n_episodic_treated, n_episodic_untreated, n_chronic_treated, n_chronic_untreated])
    st.sidebar.write(f"Total patients to simulate: {total_simulated:,}, of which:")
    st.sidebar.write(f"- Episodic Treated: {n_episodic_treated:,} ({round(n_episodic_treated/total_simulated*100)}%)")
    st.sidebar.write(f"- Episodic Untreated: {n_episodic_untreated:,} ({round(n_episodic_untreated/total_simulated*100)}%)")
    st.sidebar.write(f"- Chronic Treated: {n_chronic_treated:,} ({round(n_chronic_treated/total_simulated*100)}%)")
    st.sidebar.write(f"- Chronic Untreated: {n_chronic_untreated:,} ({round(n_chronic_untreated/total_simulated*100)}%)")

    groups_simulated = [
        ("Episodic Treated", lambda p: not p.is_chronic and p.is_treated, n_episodic_treated),
        ("Episodic Untreated", lambda p: not p.is_chronic and not p.is_treated, n_episodic_untreated),
        ("Chronic Treated", lambda p: p.is_chronic and p.is_treated, n_chronic_treated),
        ("Chronic Untreated", lambda p: p.is_chronic and not p.is_treated, n_chronic_untreated)
    ]

    # Button to run simulation
    if st.sidebar.button("Run Simulation"):
        # Run your simulation
        population = generate_population(n_episodic_treated, n_episodic_untreated, n_chronic_treated, n_chronic_untreated)
        intensities, group_data = calculate_group_data(population, groups_simulated)
        
        # Store simulation results in session state
        st.session_state.simulation_results = {
            'population': population,
            'intensities': intensities,
            'group_data': group_data,
            'ch_groups': ch_groups
        }
    
    # Sidebar title for scale transformation
    with st.sidebar.expander("Intensity Scale Transformation"):
        method_map = {
            'Linear': 'linear',
            'Piecewise Linear': 'piecewise_linear',
            'Power': 'power',
            'Power (scaled)': 'power_scaled',
            'Fitted Exponential': 'custom_exp',
            'Logarithmic': 'log'
        }
    
        # Dropdown for selecting the transformation method
        transformation_display = st.selectbox(
            "Select transformation method:",
            list(method_map.keys())
        )
        
        # Map the display name to the actual method name
        transformation_method = method_map[transformation_display]
        
        # Slider for selecting max_value
        max_value = st.number_input("Select maximum value of the scale:", min_value=10, max_value=500, value=100, step=10)
        
        # Conditional input for power if 'power' method is selected
        if transformation_method in ['power', 'power_scaled']:
            power = st.slider("Select power:", min_value=1.0, max_value=5.0, value=2.0, step=0.1)
        else:
            power = 2  # default value, won't be used for other methods
    
    # If simulation results exist, process and display them
    if 'simulation_results' in st.session_state:
        intensities = st.session_state.simulation_results['intensities']
        group_data = st.session_state.simulation_results['group_data']
        ch_groups = st.session_state.simulation_results['ch_groups']

        # Convert data to a format suitable for Plotly
        df_list = []
        global_minutes = {}
        for name, avg, std, total, n in group_data:
            df_list.append(pd.DataFrame({
                'intensity': intensities,
                'average_minutes': avg,
                'std_minutes': std,
                'total_minutes': total,
                'group': name
            }))
            # Calculate global minutes for each group
            global_total = ch_groups[name]
            global_minutes[name] = [a * global_total for a in avg]
        df = pd.concat(df_list)
    
        # Create and display average minutes plot with confidence interval
        fig_avg = go.Figure()
        avg_data = [(name, avg, std) for name, avg, std, _, _ in group_data]
        colors = px.colors.qualitative.Plotly
        markers = ['circle', 'square', 'diamond', 'cross']
        fig_avg = create_plot(fig_avg, 
                              avg_data, 
                              intensities,
                              colors, 
                              markers,
                              'Average Minutes per Year Spent at Different Pain Intensities (±1σ)',
                              'Average Minutes per Year')
        st.plotly_chart(fig_avg)
    
        # Create and display global estimated minutes plot
        # Calculate person-years for each group and intensity
        global_person_years = {}
        global_std_person_years = {}
        for name, avg, std, _, _ in group_data:
            global_total = ch_groups[name]
            global_person_years[name] = np.array([(a * global_total) / (60 * 24 * 365) for a in avg])
            global_std_person_years[name] = np.array([(s * global_total) / (60 * 24 * 365) for s in std])
        
        fig_global = go.Figure()
        global_data = [(name, global_person_years[name], global_std_person_years[name]) for name in ch_groups.keys()]
        fig_global = create_plot(fig_global,
                                 global_data,
                                 intensities,
                                 colors,
                                 markers,
                                 'Global Annual Person-Years Spent in Cluster Headaches by Intensity (±1σ)',
                                 'Global Person-Years per Year')
        st.plotly_chart(fig_global)
        
        # Calculate individual intensity person-years, high-intensity person-years, and their standard deviations
        total_person_years = {}
        high_intensity_person_years = {}
        total_std = {}
        high_intensity_std = {}
        
        for name in global_person_years.keys():
            years = global_person_years[name]
            std = global_std_person_years[name]
            
            total_years = sum(years)
            high_intensity_years = sum(years[90:])  # Sum years for intensities 9 and 10 (indices 90-100)
            
            # Calculate standard deviations using error propagation
            total_std[name] = np.sqrt(sum([s**2 for s in std]))
            high_intensity_std[name] = np.sqrt(sum([s**2 for s in std[90:]]))
            
            total_person_years[name] = total_years
            high_intensity_person_years[name] = high_intensity_years
        
        # Prepare data for both bar plots
        groups = list(total_person_years.keys())
        total_values = list(total_person_years.values())
        high_intensity_values = list(high_intensity_person_years.values())
        total_error = list(total_std.values())
        high_intensity_error = list(high_intensity_std.values())
        
        # Create and display total person-years plot
        fig_total = create_bar_plot(groups,
                                    total_values,
                                    total_error,
                                    'Total Estimated Person-Years Spent in Cluster Headaches Annually by Group',
                                    'Total Person-Years')
        st.plotly_chart(fig_total)
        
        # Create and display high-intensity person-years plot
        fig_high_intensity = create_bar_plot(groups,
                                             high_intensity_values,
                                             high_intensity_error,
                                             'Estimated Person-Years Spent in Cluster Headaches Annually by Group (Intensity ≥9/10)',
                                             'Person-Years (Intensity ≥9/10)')
       
        st.plotly_chart(fig_high_intensity)

        # Calculate total person-years for all groups
        total_all_groups = sum(total_person_years.values())
        total_all_groups_std = np.sqrt(sum([std**2 for std in total_std.values()]))
        
        # Calculate high-intensity person-years for all groups
        high_intensity_all_groups = sum(high_intensity_person_years.values())
        high_intensity_all_groups_std = np.sqrt(sum([std**2 for std in high_intensity_std.values()]))
        
        # Prepare data for the bar plot
        bar_values = [total_all_groups, high_intensity_all_groups]
        bar_errors = [total_all_groups_std, high_intensity_all_groups_std]
        
        # Call the plotting function
        fig_comparison = create_comparison_plot(bar_values, bar_errors)
        
        # Display the plot
        st.plotly_chart(fig_comparison)
        
        # Print the values
        st.write(f"Total Person-Years: {total_all_groups:,.0f} ± {total_all_groups_std:,.0f}")
        st.write(f"Person-Years at ≥9/10 Intensity: {high_intensity_all_groups:,.0f} ± {high_intensity_all_groups_std:,.0f}")

        # Calculate adjusted pain units for global estimates
        adjusted_global_pain_units = {}
        for group, years in global_person_years.items():
            adjusted_global_pain_units[group] = calculate_adjusted_pain_units(years, transformation_method, power, max_value)
    
        # Calculate adjusted pain units for average patient
        adjusted_avg_pain_units = {}
        for name, avg, _ in avg_data:
            adjusted_avg_pain_units[name] = calculate_adjusted_pain_units(avg, transformation_method, power, max_value)
    
        # Prepare the data for the adjusted plot
        adjusted_data = []
        for name in ch_groups.keys():
            values = adjusted_global_pain_units[name]
            std = [0] * len(values)
            adjusted_data.append((name, values, std))
    
        # Create the adjusted plot
        fig_adjusted = go.Figure()
        fig_adjusted = create_plot(fig_adjusted,
                                   adjusted_data,
                                   intensities,
                                   colors,
                                   markers,
                                   title=f"Intensity-Adjusted Pain Units by Cluster Headache Group ({transformation_display} Transformation)",
                                   y_title="Intensity-Adjusted Pain Units")
    
        # Update y-axis to reflect adjusted values
        max_adjusted_value = max(max(units) for units in adjusted_global_pain_units.values())
        fig_adjusted.update_layout(yaxis=dict(range=[0, max_adjusted_value * 1.1]))
    
        st.plotly_chart(fig_adjusted)
    
        # Display total adjusted person-years for each group
        st.subheader("Intensity-Adjusted Pain Units Experienced Annually")
        st.write("(Values in brackets represent adjusted pain units.)")
    
        # Create and display the summary table
        table_data = create_summary_table(ch_groups, avg_data, total_person_years, high_intensity_person_years, adjusted_global_pain_units, adjusted_avg_pain_units)
        df = create_dataframe(table_data)
        display_summary_table(df)

    else:
        st.info('Please select your parameters and then press "Run Simulation".')
        
if __name__ == "__main__":
    main()