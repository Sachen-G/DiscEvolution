import os
import json
import sys
# Add the path to the DiscEvolution directory
sys.path.append(os.path.abspath(os.path.join('..')) + '/')
sys.path.append('/Users/yuvan/GitHub/DiscEvolution/')

import numpy as np
import matplotlib.pyplot as plt

from DiscEvolution.constants import *
from DiscEvolution.grid import Grid
from DiscEvolution.star import SimpleStar
from DiscEvolution.eos import IrradiatedEOS, LocallyIsothermalEOS, SimpleDiscEOS
from DiscEvolution.disc import *
from DiscEvolution.viscous_evolution import ViscousEvolution, ViscousEvolutionFV, LBP_Solution
from DiscEvolution.disc import AccretionDisc
from DiscEvolution.dust import *
from DiscEvolution.planet_formation import *
from DiscEvolution.diffusion import TracerDiffusion
from DiscEvolution.chemistry import (
    ChemicalAbund, MolecularIceAbund, SimpleCNOAtomAbund, SimpleCNOMolAbund,
    SimpleCNOChemOberg, TimeDepCNOChemOberg, TimeDepCOChemOberg, EquilibriumCOChemMadhu,
    EquilibriumCNOChemOberg, SimpleCOAtomAbund, SimpleCOChemOberg,
    SimpleCNOChemMadhu, EquilibriumCNOChemMadhu, EquilibriumCOChemOberg
)

import numpy as np
import matplotlib.pyplot as plt
import time
start_time = time.time()
plt.rcParams.update({'font.size': 16})

#### specify separate temperature 
### initial accreation rate: 2pi r sigma radial velocity at bin 0.

def run_model(config):
    """
    Run the disk evolution model and plot the results.
    
    Parameters:
    config (dict): Configuration dictionary containing all parameters.
    """
    # Extract parameters from config
    grid_params = config['grid']
    sim_params = config['simulation']
    disc_params = config['disc']
    eos_params = config['eos']
    transport_params = config['transport']
    dust_growth_params = config['dust_growth']
    planet_params = config['planet']
    chemistry_params = config["chemistry"]
    
    # Set up disc
    # ========================
    # Create the grid
    grid = Grid(grid_params['rmin'], grid_params['rmax'], grid_params['nr'], grid_params['spacing'])
    

    # Create the star
    star = SimpleStar(M=1, R=2.5, T_eff=4000.)

    # Create time array
    if sim_params['t_interval'] == "power":
        # Determine the number of points needed
        if sim_params['t_initial'] == 0:
            num_points = int(np.log10(sim_params['t_final'])) + 1
            times = np.logspace(0, np.log10(sim_params['t_final']), num=num_points) * 2 * np.pi
        else:
            num_points = int(np.log10(sim_params['t_final'] / sim_params['t_initial'])) + 1
            times = np.logspace(np.log10(sim_params['t_initial']), np.log10(sim_params['t_final']), num=num_points) * 2 * np.pi
    elif type(sim_params['t_interval']) == list:
        times = np.array(sim_params['t_interval']) * 2 * np.pi * 1e6
    else:
        times = np.arange(sim_params['t_initial'], sim_params['t_final'], sim_params['t_interval']) * 2 * np.pi

    alpha = disc_params['alpha']

    Mdot  = disc_params["Mdot"]
    Rd    = disc_params["Rd"]
    R = grid.Rc
    Mdot *= (Msun / (2 * np.pi)) / AU**2
    #Mdot *= Msun / (2*np.pi)
    #Mdot /= AU**2

    # Create the EOS
    if eos_params["type"] == "SimpleDiscEOS":
        eos = SimpleDiscEOS(star, grid, alpha_t=alpha)
    elif eos_params["type"] == "IrradiatedEOS":
        eos = IrradiatedEOS(star, alpha_t=disc_params['alpha'], tol=1e-3)
    elif eos_params["type"] == "LocallyIsothermalEOS":
        eos = LocallyIsothermalEOS(star, eos_params['h0'], eos_params['q'], disc_params['alpha'])
    
    eos.set_grid(grid)
    #Sigma = (Mdot / (0.1 * alpha * R**2 * star.Omega_k(R))) * np.exp(-R/Rd)
    Sigma = (Mdot / (3 * np.pi * eos.nu)) * np.exp(-R/Rd)

    #redefining EOS as done in chemodynamics
    eos = IrradiatedEOS(star, alpha_t=disc_params['alpha'], tol=1e-3, accrete=False)
    eos.set_grid(grid)
    eos.update(0, Sigma)

    Sigma = (Mdot / (3 * np.pi * eos.nu)) * np.exp(-R/Rd)

    eos = IrradiatedEOS(star, alpha_t=disc_params['alpha'], tol=1e-3)
    eos.set_grid(grid)
    eos.update(0, Sigma)
    for i in range(100):
        Sigma = 0.5 * (Sigma + (Mdot / (3 * np.pi * eos.nu)) * np.exp(-R/Rd))
        eos.update(0, Sigma)

    # Set disc model
    # ========================
    try:
            #disc = DustGrowthTwoPop(grid, star, eos, disc_params['d2g'], Sigma=Sigma, Sc=disc_params['Sc'],
            #                        f_ice=dust_growth_params['f_ice'], thresh=dust_growth_params['thresh'], 
            #                        uf_0=dust_growth_params['uf_0'], uf_ice=dust_growth_params['uf_ice'], 
            #                        feedback=dust_growth_params["feedback"])
        disc = DustGrowthTwoPop(grid, star, eos, disc_params['d2g'], 
            Sigma=Sigma, feedback=dust_growth_params["feedback"]
        )
    except Exception as e:
        #disc = DustGrowthTwoPop(grid, star, eos, disc_params['d2g'], Sigma=Sigma, f_ice=dust_growth_params['f_ice'], thresh=dust_growth_params['thresh'])
        raise e

    # Set up Chemistry
    # =======================
    if chemistry_params["on"]:
        N_cell = grid_params["nr"]

        d2g = disc_params["d2g"]
        Rd = disc_params["Rd"]
        rho = Sigma / (np.sqrt(2*np.pi)*eos.H*AU)
    
        T =  eos.T
        n = Sigma / (2.4*m_H)

        if chemistry_params["chem_model"] == "Simple":
            chemistry = SimpleCOChemOberg()
        elif chemistry_params["chem_model"] == "Equilibrium":
            chemistry = EquilibriumCOChemOberg(fix_ratios=False, a=1e-5)
        elif chemistry_params["chem_model"] == "TimeDep":
            chemistry = TimeDepCOChemOberg(a=1e-5)
        else:
            raise Exception("Valid chemistry model not selected. Choose Simple, Equilibrium, or TimeDep")
        
        # Setup the dust-to-gas ratio from the chemistry
        X_solar = SimpleCOAtomAbund(N_cell) # data array containing abundances of atoms
        X_solar.set_solar_abundances() # redefines abundances by multiplying with specific constants

        # Iterate ice fractions to get the dust-to-gas ratio:
        for i in range(10):
            # Returns MolecularIceAbund class containing SimpleCOMolAbund for gas and ice
            chem = chemistry.equilibrium_chem(disc.T, 
                                            disc.midplane_gas_density,
                                            disc.dust_frac.sum(0),
                                            X_solar)
            disc.initialize_dust_density(chem.ice.total_abund)
        disc.chem = chem

        disc.update_ices(disc.chem.ice)

    # Set up dynamics
    # ========================
    gas = None
    if transport_params['gas_transport']:
        gas = ViscousEvolution()
    
    diffuse = None
    if transport_params['diffusion']:
        diffuse = TracerDiffusion(Sc=disc_params['Sc'])

    dust = None
    if transport_params['radial_drift']:
        dust = SingleFluidDrift(diffusion=diffuse)
        diffuse = None

    # Set up planet(s)
    # ========================
    if planet_params['include_planets']:
        planets = Planets(Nchem = 0)
        Mp = planet_params['Mp']
        Rp = planet_params['Rp']
        for M, R in zip(Mp, Rp):
            planets.add_planet(0, Rp, Mp, 0)

        planet_model = Bitsch2015Model(disc, pb_gas_f=0.0)

    # Run model
    # ========================
    t = 0
    n = 0
    
    # Prepare plots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    # Set up initial plot lines
    try:
        axes[0].plot(grid.Rc, 0*grid.Rc, '-', color='black', label="Gas")
        axes[0].plot(grid.Rc, 0*grid.Rc, linestyle="dashed", color='black', label="Dust")
        #axes[0].plot(grid.Rc, 0*grid.Rc, linestyle="dotted", color='black', label="Small dust")
        #axes[0].plot(grid.Rc, 0*grid.Rc, linestyle="dashed", color='black', label="Large dust")
    except:
        pass
    
    # Figure for planet growth track and planetesimal capture radius
    if planet_params['include_planets']:
        fig2, axes2 = plt.subplots(2, 1, figsize=(10, 10))
        planet_growth_track = []
        planet_capture_radius = []

    # this is to synchronize colors
    d = 0 
    colors = ["black", "red", "green", "blue", "cyan"]

    for ti in times:
        while t < ti:
            dt = ti - t
            if transport_params['gas_transport']:
                dt = min(dt, gas.max_timestep(disc))
            if transport_params['radial_drift']:
                dt = min(dt, dust.max_timestep(disc))
            
            ## old method of calculating timestep
            #if transport_params['gas_transport']:
            #    dt = gas.max_timestep(disc)
            #if transport_params['radial_drift']:
            #    dt = min(dt,dust.max_timestep(disc))
            #dt = min(dt, ti - t)
            
            # Extract updated dust frac to update gas
            dust_frac = None
            try:
                dust_frac = disc.dust_frac
            except AttributeError:
                pass

            # Extract gas tracers
            gas_chem, ice_chem = None, None
            try:
                gas_chem = disc.chem.gas.data
                ice_chem = disc.chem.ice.data
            except AttributeError:
                pass

            # Do gas evolution
            if transport_params['gas_transport']:
                gas(dt, disc, [dust_frac, gas_chem, ice_chem])

            # Do dust evolution
            if transport_params['radial_drift']:
                dust(dt, disc, gas_tracers=gas_chem, dust_tracers=ice_chem)

            if diffuse is not None:
                if gas_chem is not None:
                    gas_chem[:] += dt * diffuse(disc, gas_chem)
                if ice_chem is not None:
                    ice_chem[:] += dt * diffuse(disc, ice_chem)
                if dust_frac is not None:
                    dust_frac[:] += dt * diffuse(disc, dust_frac)

            # Pin the values to >= 0 and <=1:
            disc.Sigma[:] = np.maximum(disc.Sigma, 0)     
            disc.dust_frac[:] = np.maximum(disc.dust_frac, 0)
            disc.dust_frac[:] /= np.maximum(disc.dust_frac.sum(0), 1.0)
            if chemistry:
                disc.chem.gas.data[:] = np.maximum(disc.chem.gas.data, 0)
                disc.chem.ice.data[:] = np.maximum(disc.chem.ice.data, 0)

            
            if chemistry_params["on"]:
                chemistry.update(dt, disc.T, disc.midplane_gas_density, disc.dust_frac.sum(0), disc.chem)
                disc.update_ices(disc.chem.ice)

            if planet_params['include_planets']:
                planet_model.update() # Update internal quantities after the disc has evolved
                planet_model.integrate(dt, planets) # Update the planet masses and radii

                # Collect data for planet growth track and capture radius
                for planet in planets:
                    planet_growth_track.append((planet.R, planet.M))
                    planet_capture_radius.append((t / (2 * np.pi * 1e6), planet.R_capt))

            # Do grain growth
            disc.update(dt)
            #disc_ice.do_grain_growth(ti - t)
            
            t += dt
            n += 1

            if (n % 1000) == 0:
                print('\rNstep: {}'.format(n), end="", flush="True")
                print('\rTime: {} yr'.format(t / (2 * np.pi)), end="", flush="True")
                print('\rdt: {} yr'.format(dt / (2 * np.pi)), end="", flush="True")

        #if False:
        #    try:
        #        l, = axes[0].loglog(grid.Rc, disc.Sigma_G, label='t = {} Myr'.format(np.round(t / (2 * np.pi * 1e6), 2)))
        #        axes[0].set_xlabel('$R\\,[\\mathrm{au}]$')
        #        axes[0].set_ylabel('$\\Sigma_{\\mathrm{Gas}} [g/cm^2]$')
        #        #axes[0].set_ylim(ymin=1e-6)
        #        axes[0].set_title('Gas Surface Density')
        #        axes[0].legend()
        #    except:
        #        axes.loglog(grid.Rc, disc.Sigma_G, label='t = {} yrs'.format(np.round(t / (2 * np.pi))))
        #        axes.set_xlabel('$R\\,[\\mathrm{au}]$')
        #        axes.set_ylabel('$\\Sigma_{\\mathrm{Gas}} [g/cm^2]$')
        #        #axes.set_ylim(ymin=1e-6, ymax=1e6)
        #        axes.set_title('Gas Surface Density')
        #        axes.legend()

        if transport_params['radial_drift']:

            l, = axes[0].loglog(grid.Rc, disc.dust_frac.sum(0), linestyle="dashed", label='t = {} Myr'.format(np.round(t / (2 * np.pi * 1e6), 2)), color=colors[d])
            axes[0].set_xlabel('$R\\,[\\mathrm{au}]$')
            #axes[1].set_ylabel('$\\Sigma_{\\mathrm{Dust}} [g/cm^2]$')
            axes[0].set_ylabel('$\epsilon$')
            axes[0].set_title('Dust Fraction')
            axes[0].set_xlim(0.7, 300)
            axes[0].set_ylim(10**(-6), 10**(0))
            #axes[1].loglog(grid.Rc, (disc.Sigma_D[0]+disc.Sigma_D[1]), linestyle="dashed", color=l.get_color())

            d+=1

            axes[1].loglog(grid.Rc, disc.grain_size[1], linestyle="dashed", color=l.get_color())
            axes[1].set_xlabel('$R\\,[\\mathrm{au}]$')
            #axes[1].set_ylabel('$\\Sigma_{\\mathrm{Dust}} [g/cm^2]$')
            axes[1].set_ylabel('$a [cm]$')
            axes[1].set_title('Grain Size')
            axes[1].set_xlim(0.7, 300)
            axes[1].set_ylim(10**(-5), 10**(2))

        #if transport_params['radial_drift']:
            #axes[2].plot(grid.Rc, 0*grid.Rc, label='t = {} Myr'.format(np.round(t / (2 * np.pi * 1e6), 2)), color=l.get_color())
            #axes[2].loglog(grid.Rc, disc.v_drift[0], linestyle="dotted", color=l.get_color())
            #axes[2].loglog(grid.Rc, disc.v_drift[1], linestyle='dashed', color=l.get_color())

            #axes[2].set_xlabel('$R\\,[\\mathrm{au}]$')
            #axes[2].set_ylabel('Drift Velocity')
            #axes[2].set_ylim(ymin=1e-6)
            #axes[2].set_title('Drift Velocity')
            #axes[2].legend()
            
        if chemistry_params["on"]:
            atom_abund = disc.chem.gas.atomic_abundance()

            #l, = plt.semilogx(R, chem.gas['H2O']/mol_solar['H2O'], '-')
            #plt.semilogx(R, chem.ice['H2O']/mol_solar['H2O'],'--', c=l.get_color())
            plt.semilogx(R, atom_abund.number_abund("C")/atom_abund.number_abund("O"), label=f"{t/10**6:2f} Myr", linestyle="dashed", color=l.get_color())
            plt.xlim(0.7, 300)
            plt.ylim(0, 1.2)
            plt.ylabel('[C/O]')
            plt.legend()

            axes[2].semilogx(R, atom_abund.number_abund('C')/X_solar.number_abund("C"), label=f"{t/10**6:2f} Myr", linestyle="dashed", color=l.get_color())
            # atom_abund.number_abund('C')/X_solar.number_abund("C")
            axes[2].set_ylabel("$[C/H]_{solar}$") 
            axes[2].set_xlim(0.7, 300)
            #axes[2].set_ylim(0, 6)
            #axes[1].set_ylim(ymin=1e-6, ymax=1e6)
            #plt.semilogx(R, chem.gas['CO2'], label=f"CO2 gas: t={t:2e}")



    #plt.tight_layout()
    #plt.xlabel('Radius (AU)')

    #plt.legend(bbox_to_anchor=[1, 1])

    #plt.savefig('graphs/fixed?_H2O_abund_over_t.png', bbox_inches='tight')
    print("outputting graphs")
    fig.savefig('graphs/T&E/test_3_fixed_dust_update.png', bbox_inches='tight')

# Example usage:
# With planetesimals
#run_model(config)
#print("--- %s seconds ---" % (time.time() - start_time))
# Without planetesimals
# config['planetesimal']['include_planetesimals'] = False
# run_model(config)

# # Without planetesimals and dust
# config['planetesimal']['include_planetesimals'] = False
# config['disc']['d2g'] = 0
# config['transport']['radial_drift'] = False
# run_model(config)

if __name__ == "__main__":
    config = {
        "grid": {
            "rmin": 0.5,
            "rmax": 500,
            "nr": 1000,
            "spacing": "natural"
        },
        "simulation": {
            "t_initial": 0,
            "t_final": 1e6,
            "t_interval": [0, 0.1, 0.5, 1, 3], # Myr
        },
        "disc": {
            "alpha": 1e-3,
            "M": 0.05,
            "Rc": 35,
            "d2g": 0.01,
            "Mdot": 1e-8,
            "Sc": 1.0, # schmidt number
            "Rd": 100.
        },
        "eos": {
            "type": "LocallyIsothermalEOS",
            "h0": 1/30,
            "q": -0.25
        },
        "transport": {
            "gas_transport": True,
            "radial_drift": True,
            "diffusion": True, 
            "van_leer": True
        },
        "dust_growth": {
            "feedback": True,
            "settling": False,
            "f_ice": 0.9,           # Set ice fraction to 0
            "uf_0": 100, #500          # Fragmentation velocity for ice-free grains (cm/s)
            "uf_ice": 1000,        # Set same as uf_0 to ignore ice effects
            "thresh": 0.1        # Set high threshold to prevent ice effects
        },
        "chemistry": {
            "on"   : True, 
            "type" : "NoReact", 
            "fix_mu" : True,
            "mu"     : 2.4,
            "crate" : 1e-17,
            "use_abundance_file" : True,
            "abundances" : "Eistrup2016.dat",
            "normalize" : True,
            "variable_grain_size" : True,
            "chem_model": "Equilibrium"
        },
        "planet": {
            "include_planets": False,
            "Rp": [3],    # initial position of embryo [AU]
            "Mp": [1]     # initial mass of embryo [M_Earth]
        }
    }
    run_model(config)