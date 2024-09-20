# simulation.py
import numpy as np
from models import Patient, Attack
from SimulationConfig import SimulationConfig
from stats_utils import calculate_adjusted_pain_units, generate_attacks_per_day

class Simulation:
    def __init__(self, config):
        self.config = config
        self.population = []
        self.results = None
        self.intensities = np.arange(0, 10.1, 0.1)
        self.ch_groups = None
        self.global_person_years = {}
        self.group_data = []
        self.total_ch_sufferers = None

    def run(self):
        self.calculate_ch_groups()
        self.generate_population()
        self.simulate_year()
        self.calculate_results()
        self.calculate_adjusted_pain_units()

    def calculate_ch_groups(self):
        annual_prevalence = self.config.annual_prevalence_per_100k / 100000
        self.total_ch_sufferers = self.config.world_population * self.config.adult_fraction * annual_prevalence

        prop_chronic = self.config.prop_chronic
        prop_treated = self.config.prop_treated
        prop_episodic = self.config.prop_chronic
        prop_untreated = self.config.prop_treated

        self.ch_groups = {
            'Episodic Treated': int(self.total_ch_sufferers * self.config.prop_episodic * self.config.prop_treated),
            'Episodic Untreated': int(self.total_ch_sufferers * self.config.prop_episodic * self.config.prop_untreated),
            'Chronic Treated': int(self.total_ch_sufferers * self.config.prop_chronic * self.config.prop_treated),
            'Chronic Untreated': int(self.total_ch_sufferers * self.config.prop_chronic * self.config.prop_untreated)
        }

    def get_total_ch_sufferers(self):
        return int(self.total_ch_sufferers)
    
    def get_simulated_patients_info(self):
        fraction = self.config.percent_of_patients_to_simulate / 100
        total_simulated = int(sum(self.ch_groups.values()) * fraction)
        group_info = []
        for group, count in self.ch_groups.items():
            simulated_count = int(count * fraction)
            percentage = round(simulated_count / total_simulated * 100)
            group_info.append((group, simulated_count, percentage))
        return total_simulated, group_info
    
    def generate_population(self):
        fraction = self.config.percent_of_patients_to_simulate / 100
        for group, total in self.ch_groups.items():
            n_patients = int(total * fraction)
            is_chronic = 'Chronic' in group
            is_treated = 'Treated' in group
            for _ in range(n_patients):
                self.population.append(Patient(is_chronic, is_treated))

    def simulate_year(self):
        for patient in self.population:
            patient.generate_year_of_attacks()

    def calculate_results(self):
        group_data = []
        global_person_years = {}
        global_std_person_years = {}

        for group_name, condition in [
            ("Episodic Treated", lambda p: not p.is_chronic and p.is_treated),
            ("Episodic Untreated", lambda p: not p.is_chronic and not p.is_treated),
            ("Chronic Treated", lambda p: p.is_chronic and p.is_treated),
            ("Chronic Untreated", lambda p: p.is_chronic and not p.is_treated)
        ]:
            group_patients = [p for p in self.population if condition(p)]
            total_intensity_minutes = {}
            intensity_minutes_list = {round(i, 1): [] for i in self.intensities}
            
            for patient in group_patients:
                patient_intensity_minutes = patient.calculate_intensity_minutes()
                for intensity, minutes in patient_intensity_minutes.items():
                    rounded_intensity = round(intensity, 1)
                    total_intensity_minutes[rounded_intensity] = total_intensity_minutes.get(rounded_intensity, 0) + minutes
                    intensity_minutes_list[rounded_intensity].append(minutes)

            n_patients = len(group_patients)
            intensity_minutes_average = [total_intensity_minutes.get(round(i, 1), 0) / n_patients for i in self.intensities]
            intensity_minutes_std = [np.std(intensity_minutes_list[round(i, 1)]) if intensity_minutes_list[round(i, 1)] else 0 for i in self.intensities]
            intensity_minutes_total = [total_intensity_minutes.get(round(i, 1), 0) for i in self.intensities]
            
            group_data.append((group_name, intensity_minutes_average, intensity_minutes_std, intensity_minutes_total, n_patients))

            global_total = self.ch_groups[group_name]
            global_person_years[group_name] = np.array([(a * global_total) / (60 * 24 * 365) for a in intensity_minutes_average])
            global_std_person_years[group_name] = np.array([(s * global_total) / (60 * 24 * 365) for s in intensity_minutes_std])

        self.group_data = group_data
        self.global_person_years = global_person_years
        self.global_std_person_years = global_std_person_years

    def calculate_adjusted_pain_units(self):
        self.adjusted_pain_units = {}
        self.adjusted_avg_pain_units = {}
        for group in self.ch_groups.keys():
            self.adjusted_pain_units[group] = calculate_adjusted_pain_units(
                self.global_person_years[group],
                self.intensities,
                self.config.transformation_method,
                self.config.power,
                self.config.max_value
            )
            avg_data = next(avg for name, avg, _, _, _ in self.group_data if name == group)
            self.adjusted_avg_pain_units[group] = calculate_adjusted_pain_units(
                avg_data,
                self.intensities,
                self.config.transformation_method,
                self.config.power,
                self.config.max_value
            )

    def update_transformation_params(self, transformation_method, power, max_value):
        self.config.transformation_method = transformation_method
        self.config.power = power
        self.config.max_value = max_value
        self.calculate_adjusted_pain_units()
        
    def get_results(self):
        return {
            'intensities': self.intensities,
            'group_data': self.group_data,
            'global_person_years': self.global_person_years,
            'global_std_person_years': self.global_std_person_years,
            'ch_groups': self.ch_groups,
            'adjusted_pain_units': self.adjusted_pain_units,
            'adjusted_avg_pain_units': self.adjusted_avg_pain_units,
            'calculate_adjusted_pain_units': calculate_adjusted_pain_units  # Include the function itself
        }